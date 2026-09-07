"""Voice Lab: record or import sounds, convert voices, chain effects, keep a library.

Runs on the CPU inside WSL2; open http://localhost:7860 in a Windows browser.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

import gradio as gr
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402
from audio import duration, load, median_f0, peak_normalize  # noqa: E402
from effects import REGISTRY, apply_chain, by_category  # noqa: E402
from effects.tts import FEMALE, VOICES as KOKORO_VOICES, synthesize  # noqa: E402


def _ffmpeg_on_path() -> None:
    """Give pydub/gradio an ffmpeg without apt: imageio-ffmpeg bundles a static binary."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        shim = Path.home() / ".cache" / "voice-lab" / "bin"
        shim.mkdir(parents=True, exist_ok=True)
        link = shim / "ffmpeg"
        if not link.exists():
            link.symlink_to(exe)
        os.environ["PATH"] = f"{shim}{os.pathsep}{os.environ.get('PATH', '')}"
    except Exception:
        pass


_ffmpeg_on_path()

DEFAULT_TEXT = ("Docking clearance granted. Hold your approach vector and cut thrust at two hundred metres. "
                "Welcome to Meridian Port; the harbour master will be with you shortly.")


# ----------------------------------------------------------------------------- shared helpers
def _err(message: str):
    raise gr.Error(message)


def _sources():
    names = library.list_sources()
    return gr.update(choices=names, value=names[-1] if names else None)


def _voices():
    names = library.list_voices()
    return gr.update(choices=names, value=names[-1] if names else None)


def _audio_choices():
    choices = library.all_audio_choices()
    return gr.update(choices=choices, value=choices[0] if choices else None)


def _presets():
    names = library.list_presets()
    return gr.update(choices=names, value=names[0] if names else None)


def _chain_summary(chain) -> str:
    return " > ".join(REGISTRY[s["name"]].label if s["name"] in REGISTRY else s["name"] for s in (chain or []))


def _renders_rows():
    return [[r["name"], r.get("seconds", ""), r.get("label", ""), _chain_summary(r.get("chain")), r.get("notes", "")] for r in library.list_renders()]


def _f0_note(audio, sr, out, out_sr) -> str:
    f_in, f_out = median_f0(audio, sr), median_f0(out, out_sr)
    fmt = lambda f: f"{f:.0f} Hz" if f else "n/a"
    return f"median pitch {fmt(f_in)} -> {fmt(f_out)}"


# ----------------------------------------------------------------------------- sources
def save_source(audio_path, name):
    if not audio_path:
        _err("Record or upload something first.")
    fname = library.add_source(audio_path, name)
    return f"Saved sources/{fname}", _sources(), _audio_choices()


def preview_source(name):
    return library.source_path(name) if name else None


# ----------------------------------------------------------------------------- voices
def make_voice(name, text, kokoro_voice, speed):
    if not text.strip():
        _err("Give the voice something to say.")
    t = time.time()
    audio, sr = synthesize(text, kokoro_voice, speed)
    audio = peak_normalize(audio)
    vname = library.add_voice(name or kokoro_voice, audio, sr, {"text": text, "kokoro_voice": kokoro_voice, "speed": speed})
    return (sr, audio), f"Saved voice '{vname}' ({duration(audio, sr):.1f}s in {time.time() - t:.1f}s)", _voices(), _audio_choices()


def import_voice(path, name):
    if not path:
        _err("Upload a wav of the target voice first.")
    audio, sr = load(path)
    vname = library.add_voice(name or Path(path).stem, peak_normalize(audio), sr, {"imported": Path(path).name})
    return (sr, audio), f"Imported voice '{vname}'", _voices(), _audio_choices()


def preview_voice(name):
    return library.voice_path(name) if name else None


# ----------------------------------------------------------------------------- convert
def convert(source, voice, model, keep_contour, semitones, auto_f0, steps, cfg, v2_style, v2_intel, v2_sim, label):
    if not source:
        _err("Pick a source recording (Sources tab).")
    if not voice:
        _err("Pick a target voice (Voices tab).")
    audio, sr = load(library.source_path(source))
    if model == "v1":
        chain = [{"name": "voice_convert", "params": {"voice": voice, "keep_pitch_contour": bool(keep_contour), "semitones": int(semitones),
                                                      "auto_f0": bool(auto_f0), "steps": int(steps), "cfg": float(cfg), "engine": "inproc"}}]
    else:
        chain = [{"name": "voice_convert_v2", "params": {"voice": voice, "convert_style": bool(v2_style), "steps": int(steps),
                                                         "intelligibility": float(v2_intel), "similarity": float(v2_sim)}}]
    t = time.time()
    try:
        out, out_sr = apply_chain(audio, sr, chain)
    except Exception as e:  # surface the real reason in the UI
        traceback.print_exc()
        _err(f"Conversion failed: {e}")
    out = peak_normalize(out)
    name = library.save_render(out, out_sr, {"label": label or f"{Path(source).stem} as {voice}", "input": f"source:{source}", "chain": chain},
                               label=label or f"{voice}-{model}")
    status = f"{time.time() - t:.0f}s for {duration(audio, sr):.1f}s of audio; {_f0_note(audio, sr, out, out_sr)}; saved renders/{name}.wav"
    return (out_sr, out), library.source_path(source), status, _renders_rows(), _audio_choices()


# ----------------------------------------------------------------------------- effect chains
def add_effect(effect_name, chain):
    chain = list(chain or [])
    if effect_name in REGISTRY:
        chain.append({"name": effect_name, "params": REGISTRY[effect_name].defaults()})
    print(f"[chain] add {effect_name!r} -> {len(chain)} step(s)", flush=True)
    return chain


def replace_chain_json(text, chain):
    try:
        data = json.loads(text)
        assert isinstance(data, list) and all(s.get("name") in REGISTRY for s in data)
    except Exception:
        _err("Chain JSON must be a list of {name, params} with known effect names.")
    return data


def run_chain(input_choice, chain, label):
    if not input_choice:
        _err("Pick an input.")
    if not chain:
        _err("Add at least one effect.")
    audio, sr = load(library.resolve_choice(input_choice))
    logs = []
    t = time.time()
    try:
        out, out_sr = apply_chain(audio, sr, chain, log=logs.append)
    except Exception as e:
        traceback.print_exc()
        _err(f"Chain failed: {e}")
    out = peak_normalize(out)
    name = library.save_render(out, out_sr, {"label": label or _chain_summary(chain), "input": input_choice, "chain": chain}, label=label or "chain")
    return (out_sr, out), f"{time.time() - t:.1f}s; " + ", ".join(logs) + f"; saved renders/{name}.wav", _renders_rows(), _audio_choices()


def save_preset(name, chain, notes):
    if not name.strip():
        _err("Name the preset.")
    if not chain:
        _err("The chain is empty.")
    pname = library.save_preset(name, chain, notes)
    return f"Saved preset '{pname}'", _presets()


def load_preset(name):
    return library.load_preset(name) if name else []


def delete_preset(name):
    if name:
        library.delete_preset(name)
    return _presets()


# ----------------------------------------------------------------------------- library
def select_render(evt: gr.SelectData, rows):
    if evt.index is None or not rows:
        return None, "", ""
    name = rows[evt.index[0]][0]
    notes = next((r.get("notes", "") for r in library.list_renders() if r["name"] == name), "")
    return name, library.render_path(name), notes


def save_notes(name, notes):
    if name:
        library.set_render_notes(name, notes)
    return _renders_rows()


def delete_render(name):
    if name:
        library.delete_render(name)
    return None, None, _renders_rows(), _audio_choices()


# ----------------------------------------------------------------------------- UI
CSS = """
.gradio-container { max-width: 1280px !important; }
.status { font-family: ui-monospace, monospace; font-size: 0.9em; }
"""

with gr.Blocks(title="Voice Lab", css=CSS, theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Voice Lab\nRecord, convert, mangle, keep. Everything runs locally on the CPU.")

    # ---- Sources
    with gr.Tab("Sources"):
        with gr.Row():
            with gr.Column():
                rec = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record or upload a take (wav)")
                rec_name = gr.Textbox(label="Name", placeholder="harbour master line 3")
                rec_save = gr.Button("Save to sources", variant="primary")
                rec_status = gr.Markdown(elem_classes="status")
            with gr.Column():
                src_list = gr.Dropdown(choices=library.list_sources(), label="Saved sources", interactive=True)
                src_refresh = gr.Button("Refresh")
                src_play = gr.Audio(label="Preview", type="filepath")

    # ---- Voices
    with gr.Tab("Voices"):
        gr.Markdown("A reference voice is a clean 10-20 second clip. Synthesise one with Kokoro so the character is nobody's real voice, or import a wav you have the right to use.")
        with gr.Row():
            with gr.Column():
                v_name = gr.Textbox(label="Voice name", placeholder="harbour-master")
                v_text = gr.Textbox(label="Text", value=DEFAULT_TEXT, lines=3)
                v_kokoro = gr.Dropdown(choices=KOKORO_VOICES, value=FEMALE[0], label="Kokoro voice (af/bf female, am/bm male)")
                v_speed = gr.Slider(0.6, 1.4, value=1.0, step=0.05, label="Speed")
                v_make = gr.Button("Synthesise reference voice", variant="primary")
                v_upload = gr.Audio(sources=["upload"], type="filepath", label="Or import a reference wav")
                v_import = gr.Button("Import as voice")
                v_status = gr.Markdown(elem_classes="status")
            with gr.Column():
                v_out = gr.Audio(label="Reference", type="numpy")
                v_list = gr.Dropdown(choices=library.list_voices(), label="Saved voices", interactive=True)
                v_play = gr.Audio(label="Preview", type="filepath")

    # ---- Convert
    with gr.Tab("Convert"):
        with gr.Row():
            with gr.Column():
                c_source = gr.Dropdown(choices=library.list_sources(), label="Source take")
                c_voice = gr.Dropdown(choices=library.list_voices(), label="Target voice")
                c_model = gr.Radio(choices=["v1", "v2"], value="v1", label="Model",
                                   info="v1: timbre conversion, fastest, pitch controls. v2: also converts accent and emotion, slower.")
                with gr.Group():
                    c_keep = gr.Checkbox(value=False, label="Keep my pitch contour (v1 F0 model)",
                                         info="Off: pitch is re-synthesised in the reference's range. On: your melody is kept and moved.")
                    c_autof0 = gr.Checkbox(value=True, label="Auto-match pitch level to the reference (F0 model)")
                    c_semi = gr.Slider(-12, 16, value=0, step=1, label="Extra semitone shift on top (F0 model)",
                                       info="With auto-match on, leave at 0; without it, 6-10 is the male-to-female range.")
                    c_steps = gr.Slider(4, 60, value=25, step=1, label="Diffusion steps (fewer = faster drafts)")
                    c_cfg = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Guidance (v1)")
                with gr.Accordion("v2 options", open=False):
                    c_v2_style = gr.Checkbox(value=True, label="Convert accent and emotion too")
                    c_v2_intel = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Intelligibility")
                    c_v2_sim = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Similarity")
                c_label = gr.Textbox(label="Render label (optional)")
                c_go = gr.Button("Convert", variant="primary")
                c_status = gr.Markdown(elem_classes="status")
            with gr.Column():
                c_out = gr.Audio(label="Converted", type="numpy")
                c_ab = gr.Audio(label="Original, for A/B", type="filepath")

    # ---- Effects chain
    with gr.Tab("Effects chain"):
        chain_state = gr.State([])
        with gr.Row():
            with gr.Column(scale=3):
                e_input = gr.Dropdown(choices=library.all_audio_choices(), label="Input (source, render or voice)")
                with gr.Row():
                    e_pick = gr.Dropdown(choices=[e.name for cat in by_category().values() for e in cat], label="Effect",
                                         info="voice: conversion and TTS. dsp: pedalboard and numpy processors. utility: housekeeping.")
                    e_add = gr.Button("Add to chain")
                e_refresh = gr.Button("Refresh inputs and voices")

                @gr.render(inputs=[chain_state])
                def render_chain(chain):
                    print(f"[chain] render {len(chain or [])} step(s)", flush=True)
                    if not chain:
                        gr.Markdown("*Chain is empty. Add an effect above, or load a preset.*")
                    for i, step in enumerate(chain):
                        eff = REGISTRY.get(step["name"])
                        if eff is None:
                            continue
                        with gr.Group():
                            with gr.Row():
                                gr.Markdown(f"**{i + 1}. {eff.label}**  <span style='opacity:.6'>{eff.help}</span>")
                                up = gr.Button("Up", size="sm", scale=0)
                                rm = gr.Button("Remove", size="sm", scale=0, variant="stop")
                            with gr.Row():
                                for p in eff.params:
                                    value = step.get("params", {}).get(p.name, p.default)
                                    if p.kind in ("float", "int"):
                                        comp = gr.Slider(p.min, p.max, value=value, step=p.step or (1 if p.kind == "int" else None), label=p.label, info=p.help or None)
                                        event = comp.release
                                    elif p.kind == "bool":
                                        comp = gr.Checkbox(value=bool(value), label=p.label, info=p.help or None)
                                        event = comp.change
                                    elif p.kind == "choice":
                                        comp = gr.Dropdown(choices=p.choices, value=value, label=p.label)
                                        event = comp.change
                                    elif p.kind == "voice":
                                        voices = library.list_voices()
                                        comp = gr.Dropdown(choices=voices, value=value if value in voices else (voices[-1] if voices else None), label=p.label)
                                        event = comp.change
                                    else:
                                        comp = gr.Textbox(value=str(value), label=p.label, lines=2)
                                        event = comp.blur

                                    def setter(value, chain, i=i, pname=p.name, kind=p.kind):
                                        chain = json.loads(json.dumps(chain))
                                        if kind == "int":
                                            value = int(value)
                                        chain[i].setdefault("params", {})[pname] = value
                                        return chain
                                    event(setter, inputs=[comp, chain_state], outputs=[chain_state])

                            def remove(chain, i=i):
                                chain = list(chain); chain.pop(i); return chain

                            def move_up(chain, i=i):
                                chain = list(chain)
                                if i > 0:
                                    chain[i - 1], chain[i] = chain[i], chain[i - 1]
                                return chain
                            rm.click(remove, inputs=[chain_state], outputs=[chain_state])
                            up.click(move_up, inputs=[chain_state], outputs=[chain_state])

                with gr.Accordion("Chain as JSON", open=False):
                    e_json = gr.Code(language="json", label="Chain")
                    e_json_apply = gr.Button("Replace chain with this JSON")
                e_label = gr.Textbox(label="Render label (optional)")
                e_run = gr.Button("Apply chain", variant="primary")
                e_status = gr.Markdown(elem_classes="status")
            with gr.Column(scale=2):
                e_out = gr.Audio(label="Result", type="numpy")
                with gr.Group():
                    gr.Markdown("**Presets**")
                    p_list = gr.Dropdown(choices=library.list_presets(), label="Saved presets")
                    with gr.Row():
                        p_load = gr.Button("Load")
                        p_delete = gr.Button("Delete", variant="stop")
                    p_name = gr.Textbox(label="Save current chain as")
                    p_notes = gr.Textbox(label="Notes", lines=2)
                    p_save = gr.Button("Save preset")
                    p_status = gr.Markdown(elem_classes="status")

    # ---- Library
    with gr.Tab("Library"):
        l_selected = gr.State(None)
        l_table = gr.Dataframe(headers=["name", "seconds", "label", "chain", "notes"], datatype=["str", "number", "str", "str", "str"],
                               value=_renders_rows(), interactive=False, wrap=True)
        with gr.Row():
            with gr.Column():
                l_play = gr.Audio(label="Selected render", type="filepath")
            with gr.Column():
                l_notes = gr.Textbox(label="Notes", lines=3)
                with gr.Row():
                    l_save_notes = gr.Button("Save notes")
                    l_delete = gr.Button("Delete render", variant="stop")

    # ---- wiring
    rec_save.click(save_source, [rec, rec_name], [rec_status, src_list, e_input]).then(lambda: _sources(), None, c_source)
    src_refresh.click(lambda: _sources(), None, src_list)
    src_list.change(preview_source, src_list, src_play)

    v_make.click(make_voice, [v_name, v_text, v_kokoro, v_speed], [v_out, v_status, v_list, e_input]).then(lambda: _voices(), None, c_voice)
    v_import.click(import_voice, [v_upload, v_name], [v_out, v_status, v_list, e_input]).then(lambda: _voices(), None, c_voice)
    v_list.change(preview_voice, v_list, v_play)

    c_go.click(convert, [c_source, c_voice, c_model, c_keep, c_semi, c_autof0, c_steps, c_cfg, c_v2_style, c_v2_intel, c_v2_sim, c_label],
               [c_out, c_ab, c_status, l_table, e_input])

    e_add.click(add_effect, [e_pick, chain_state], [chain_state])
    e_refresh.click(lambda: _audio_choices(), None, e_input)
    chain_state.change(lambda chain: json.dumps(chain, indent=2), chain_state, e_json)
    e_json_apply.click(replace_chain_json, [e_json, chain_state], [chain_state])
    e_run.click(run_chain, [e_input, chain_state, e_label], [e_out, e_status, l_table, e_input])
    p_save.click(save_preset, [p_name, chain_state, p_notes], [p_status, p_list])
    p_load.click(load_preset, p_list, chain_state)
    p_delete.click(delete_preset, p_list, p_list)

    l_table.select(select_render, [l_table], [l_selected, l_play, l_notes])
    l_save_notes.click(save_notes, [l_selected, l_notes], [l_table])
    l_delete.click(delete_render, [l_selected], [l_selected, l_play, l_table, e_input])

    # refresh dropdowns whenever a tab is opened
    demo.load(lambda: (_sources(), _voices(), _audio_choices(), _presets(), _renders_rows()), None, [c_source, c_voice, e_input, p_list, l_table])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="127.0.0.1", server_port=int(os.environ.get("PORT", "7860")),
                                                    show_api=os.environ.get("VOICE_LAB_SHOW_API") == "1", inbrowser=False, share=False)
