"""Voice Lab: record or import a take, convert the voice, chain effects, keep a library.

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
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402
from audio import duration, load, median_f0, peak_normalize  # noqa: E402
from effects import REGISTRY, apply_chain, by_category  # noqa: E402
from effects.tts import FEMALE, MALE, synthesize  # noqa: E402


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
SECONDS_PER_SECOND_AT_15_STEPS = 9.0          # measured on this laptop, v1, models warm
CATEGORY_LABEL = {"voice": "Voice", "dsp": "DSP", "utility": "Utility"}


# ----------------------------------------------------------------------------- shared helpers
def _err(message: str):
    raise gr.Error(message)


def _sources(prefer=None):
    names = library.list_sources()
    return gr.update(choices=names, value=prefer if prefer in names else (names[-1] if names else None))


def _voices(prefer=None):
    names = library.list_voices()
    return gr.update(choices=names, value=prefer if prefer in names else (names[-1] if names else None))


def _audio_choices(prefer=None):
    choices = library.all_audio_choices()
    return gr.update(choices=choices, value=prefer if prefer in choices else (choices[0] if choices else None))


def _presets(prefer=None):
    names = library.list_presets()
    return gr.update(choices=names, value=prefer if prefer in names else (names[0] if names else None))


def _effect_choices():
    return [(f"{CATEGORY_LABEL.get(cat, cat)} · {e.label}", e.name) for cat, effects in by_category().items() for e in effects]


def _kokoro_choices():
    return [(f"Female · {v}", v) for v in FEMALE] + [(f"Male · {v}", v) for v in MALE]


def _chain_summary(chain) -> str:
    return " › ".join(REGISTRY[s["name"]].label if s["name"] in REGISTRY else s["name"] for s in (chain or []))


def _when(name: str) -> str:
    stamp = name.split("_", 1)[0]
    return f"{stamp[6:8]}/{stamp[4:6]} {stamp[9:11]}:{stamp[11:13]}" if len(stamp) >= 13 else ""


def _renders_rows():
    return [[r.get("label", ""), _when(r["name"]), r.get("seconds", ""), _chain_summary(r.get("chain")), r.get("notes", "")]
            for r in library.list_renders()]


def _render_names():
    return [r["name"] for r in library.list_renders()]


def _f0_note(audio, sr, out, out_sr) -> str:
    f_in, f_out = median_f0(audio, sr), median_f0(out, out_sr)
    fmt = lambda f: f"{f:.0f} Hz" if f else "n/a"
    return f"pitch {fmt(f_in)} → {fmt(f_out)}"


def _estimate(source, steps, model):
    if not source:
        return ""
    try:
        info = sf.info(library.source_path(source))
        seconds = info.frames / info.samplerate
    except Exception:
        return ""
    est = seconds * SECONDS_PER_SECOND_AT_15_STEPS * (float(steps) / 15.0) * (1.6 if model == "v2" else 1.0)
    return f"<span class='muted'>{seconds:.1f} s take · about {est / 60:.1f} min of compute at {int(steps)} steps</span>"


# ----------------------------------------------------------------------------- takes and voices
def save_take(audio_path, name):
    if not audio_path:
        _err("Record or upload something first.")
    fname = library.add_source(audio_path, name)
    return f"Saved take {fname}", _sources(fname), _audio_choices()


def make_voice(name, text, kokoro_voice, speed):
    if not text.strip():
        _err("Give the voice something to say.")
    t = time.time()
    audio, sr = synthesize(text, kokoro_voice, speed)
    audio = peak_normalize(audio)
    vname = library.add_voice(name or kokoro_voice, audio, sr, {"text": text, "kokoro_voice": kokoro_voice, "speed": speed})
    return f"Saved voice {vname} · {duration(audio, sr):.1f} s in {time.time() - t:.1f} s", _voices(vname), _audio_choices()


def import_voice(path, name):
    if not path:
        _err("Upload a wav of the target voice first.")
    audio, sr = load(path)
    vname = library.add_voice(name or Path(path).stem, peak_normalize(audio), sr, {"imported": Path(path).name})
    return f"Imported voice {vname}", _voices(vname), _audio_choices()


def preview_voice(name):
    return library.voice_path(name) if name else None


# ----------------------------------------------------------------------------- convert
def convert(source, voice, model, steps, cfg, keep_contour, auto_f0, semitones, v2_style, v2_intel, v2_sim, label):
    if not source:
        _err("Pick a take.")
    if not voice:
        _err("Pick a voice.")
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
    except Exception as e:
        traceback.print_exc()
        _err(f"Conversion failed: {e}")
    out = peak_normalize(out)
    name = library.save_render(out, out_sr, {"label": label or f"{voice} · {model}", "input": f"source:{source}", "chain": chain},
                               label=label or f"{voice}-{model}")
    status = f"{time.time() - t:.0f} s · {_f0_note(audio, sr, out, out_sr)} · saved as {name}"
    return (out_sr, out), library.source_path(source), status, _renders_rows(), _render_names(), _audio_choices()


# ----------------------------------------------------------------------------- effect chains
def add_effect(effect_name, chain):
    chain = list(chain or [])
    if effect_name in REGISTRY:
        chain.append({"name": effect_name, "params": REGISTRY[effect_name].defaults()})
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
    return (out_sr, out), f"{time.time() - t:.1f} s · " + ", ".join(logs) + f" · saved as {name}", _renders_rows(), _render_names(), _audio_choices()


def save_preset(name, chain, notes):
    if not name.strip():
        _err("Name the preset.")
    if not chain:
        _err("The chain is empty.")
    pname = library.save_preset(name, chain, notes)
    return f"Saved preset {pname}", _presets(pname), ""


def load_preset(name):
    return library.load_preset(name) if name else []


def delete_preset(name):
    if name:
        library.delete_preset(name)
    return _presets()


# ----------------------------------------------------------------------------- library
def select_render(evt: gr.SelectData, names):
    if evt.index is None or not names or evt.index[0] >= len(names):
        return None, None, ""
    name = names[evt.index[0]]
    notes = next((r.get("notes", "") for r in library.list_renders() if r["name"] == name), "")
    return name, library.render_path(name), notes


def save_notes(name, notes):
    if name:
        library.set_render_notes(name, notes)
    return _renders_rows(), _render_names()


def delete_render(name):
    if name:
        library.delete_render(name)
    return None, None, _renders_rows(), _render_names(), _audio_choices()


# ----------------------------------------------------------------------------- UI
THEME = gr.themes.Base(primary_hue=gr.themes.colors.sky, neutral_hue=gr.themes.colors.slate,
                       font=["ui-sans-serif", "system-ui", "sans-serif"], font_mono=["ui-monospace", "monospace"]).set(
    block_label_text_size="*text_xs", block_title_text_size="*text_sm", block_padding="10px 12px",
    layout_gap="10px", block_radius="10px", input_padding="6px 10px", button_large_padding="10px 18px")

CSS = """
/* body is a flex column: an explicit width stops the container shrinking to its content */
.gradio-container { width: 100% !important; max-width: 1240px !important; margin: 0 auto !important; }
footer { display: none !important; }
.muted { opacity: .62; font-size: .86em; }
.status { font-family: ui-monospace, monospace; font-size: .82em; opacity: .8; min-height: 1.4em; }
.title h2 { margin: 0 0 .1em 0; font-weight: 600; letter-spacing: .01em; }
.step .prose { font-size: .92em; }
.tight > .form, .tight .block { padding: 6px 8px !important; }
"""

FORCE_DARK = "() => { document.body.classList.add('dark'); }"


with gr.Blocks(title="Voice Lab", theme=THEME, css=CSS, js=FORCE_DARK) as demo:
    with gr.Row():
        gr.Markdown("## Voice Lab", elem_classes="title")
        gr.Markdown("<span class='muted'>local · CPU · nothing leaves the laptop</span>")

    with gr.Tabs() as tabs:
        # =================================================================== Convert
        with gr.Tab("Convert", id="convert"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=5, min_width=380):
                    c_source = gr.Dropdown(choices=library.list_sources(), label="Take")
                    with gr.Accordion("Record or upload a take", open=False):
                        rec = gr.Audio(sources=["microphone", "upload"], type="filepath", show_label=False)
                        with gr.Row():
                            rec_name = gr.Textbox(label="Name", placeholder="harbour master, line 3", scale=3)
                            rec_save = gr.Button("Save take", scale=1, min_width=110)
                        rec_status = gr.Markdown(elem_classes="status")

                    c_voice = gr.Dropdown(choices=library.list_voices(), label="Voice")
                    with gr.Accordion("Voice preview and new voices", open=False):
                        v_play = gr.Audio(label="Reference", type="filepath")
                        gr.Markdown("<span class='muted'>A reference is a clean 10–20 s clip. Synthesise one so the character is nobody's real voice.</span>")
                        v_kokoro = gr.Dropdown(choices=_kokoro_choices(), value=FEMALE[0], label="Kokoro voice")
                        v_text = gr.Textbox(label="Text", value=DEFAULT_TEXT, lines=2)
                        with gr.Row():
                            v_speed = gr.Slider(0.6, 1.4, value=1.0, step=0.05, label="Speed", scale=2)
                            v_name = gr.Textbox(label="Name", placeholder="harbour-master", scale=2)
                            v_make = gr.Button("Synthesise", scale=1, min_width=110)
                        with gr.Row():
                            v_upload = gr.Audio(sources=["upload"], type="filepath", label="Or import a wav", scale=3)
                            v_import = gr.Button("Import", scale=1, min_width=110)
                        v_status = gr.Markdown(elem_classes="status")

                    c_model = gr.Radio(choices=[("v1 · timbre", "v1"), ("v2 · timbre, accent and emotion", "v2")], value="v1", label="Model")
                    c_go = gr.Button("Convert", variant="primary", size="lg")
                    c_estimate = gr.Markdown()
                    with gr.Accordion("Tuning", open=False):
                        c_steps = gr.Slider(4, 60, value=15, step=1, label="Diffusion steps", info="Quality against time. 8–10 for drafts.")
                        c_cfg = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Guidance (v1)")
                        c_keep = gr.Checkbox(value=False, label="Keep my pitch contour (v1 F0 model)",
                                             info="Off: pitch re-synthesised in the voice's range. On: your melody kept and moved.")
                        with gr.Row():
                            c_autof0 = gr.Checkbox(value=True, label="Auto-match pitch level", scale=1)
                            c_semi = gr.Slider(-12, 16, value=0, step=1, label="Extra semitones", scale=2)
                        with gr.Row():
                            c_v2_style = gr.Checkbox(value=True, label="v2: convert accent and emotion", scale=1)
                            c_v2_intel = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="v2 intelligibility", scale=1)
                            c_v2_sim = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="v2 similarity", scale=1)
                        c_label = gr.Textbox(label="Render label", placeholder="optional")
                with gr.Column(scale=7, min_width=420):
                    c_out = gr.Audio(label="Converted", type="numpy")
                    c_ab = gr.Audio(label="Original", type="filepath")
                    c_status = gr.Markdown(elem_classes="status")

        # =================================================================== Effects
        with gr.Tab("Effects", id="effects"):
            chain_state = gr.State([])
            with gr.Row(equal_height=False):
                with gr.Column(scale=7, min_width=460):
                    e_input = gr.Dropdown(choices=library.all_audio_choices(), label="Input")
                    with gr.Row():
                        e_pick = gr.Dropdown(choices=_effect_choices(), label="Effect", scale=4)
                        e_add = gr.Button("Add", scale=1, min_width=90)

                    @gr.render(inputs=[chain_state])
                    def render_chain(chain):
                        if not chain:
                            gr.Markdown("<span class='muted'>No effects yet. Add one above or load a preset.</span>")
                        for i, step in enumerate(chain):
                            eff = REGISTRY.get(step["name"])
                            if eff is None:
                                continue
                            # Stable keys let Gradio keep these components across re-renders, so a drag is not interrupted.
                            with gr.Group(key=f"step-{i}", elem_classes="step"):
                                with gr.Row(key=f"step-{i}-head"):
                                    with gr.Column(scale=6, min_width=200, key=f"step-{i}-titlecol"):
                                        gr.Markdown(f"**{i + 1}. {eff.label}**", key=f"step-{i}-title")
                                    up = gr.Button("▲", size="sm", scale=0, min_width=44, key=f"step-{i}-up")
                                    rm = gr.Button("✕", size="sm", scale=0, min_width=44, variant="stop", key=f"step-{i}-rm")
                                if eff.params:
                                    with gr.Row(key=f"step-{i}-params"):
                                        for p in eff.params:
                                            value = step.get("params", {}).get(p.name, p.default)
                                            key = f"step-{i}-{p.name}"
                                            if p.kind in ("float", "int"):
                                                comp = gr.Slider(p.min, p.max, value=value, step=p.step or (1 if p.kind == "int" else None), label=p.label, key=key)
                                                events = (comp.release, comp.change)      # drags commit on release, typed values on change
                                            elif p.kind == "bool":
                                                comp = gr.Checkbox(value=bool(value), label=p.label, key=key)
                                                events = (comp.change,)
                                            elif p.kind == "choice":
                                                comp = gr.Dropdown(choices=p.choices, value=value, label=p.label, key=key)
                                                events = (comp.change,)
                                            elif p.kind == "voice":
                                                voices = library.list_voices()
                                                comp = gr.Dropdown(choices=voices, value=value if value in voices else (voices[-1] if voices else None), label=p.label, key=key)
                                                events = (comp.change,)
                                            else:
                                                comp = gr.Textbox(value=str(value), label=p.label, lines=2, key=key)
                                                events = (comp.blur,)

                                            def setter(value, chain, i=i, pname=p.name, kind=p.kind):
                                                chain = json.loads(json.dumps(chain))
                                                if kind == "int":
                                                    value = int(value)
                                                if chain[i].setdefault("params", {}).get(pname) == value:
                                                    return gr.skip()
                                                chain[i]["params"][pname] = value
                                                return chain
                                            for event in events:
                                                event(setter, inputs=[comp, chain_state], outputs=[chain_state], trigger_mode="always_last", show_progress="hidden")

                                def remove(chain, i=i):
                                    chain = list(chain); chain.pop(i); return chain

                                def move_up(chain, i=i):
                                    chain = list(chain)
                                    if i > 0:
                                        chain[i - 1], chain[i] = chain[i], chain[i - 1]
                                    return chain
                                rm.click(remove, inputs=[chain_state], outputs=[chain_state], show_progress="hidden")
                                up.click(move_up, inputs=[chain_state], outputs=[chain_state], show_progress="hidden")

                    with gr.Row():
                        e_label = gr.Textbox(label="Render label", placeholder="optional", scale=3)
                        e_run = gr.Button("Apply chain", variant="primary", scale=2, min_width=140)
                    e_status = gr.Markdown(elem_classes="status")
                    with gr.Accordion("Chain as JSON", open=False):
                        e_json = gr.Code(language="json", show_label=False)
                        e_json_apply = gr.Button("Replace chain with this JSON", size="sm")
                    with gr.Accordion("What the effects do", open=False):
                        gr.Markdown("\n".join(f"- **{e.label}** ({CATEGORY_LABEL.get(cat, cat)}): {e.help or ', '.join(p.label for p in e.params) or '—'}"
                                              for cat, effects in by_category().items() for e in effects))
                with gr.Column(scale=5, min_width=360):
                    e_out = gr.Audio(label="Result", type="numpy")
                    gr.Markdown("**Presets**")
                    with gr.Row():
                        p_list = gr.Dropdown(choices=library.list_presets(), show_label=False, scale=3)
                        p_load = gr.Button("Load", size="sm", scale=1, min_width=70)
                        p_delete = gr.Button("Delete", size="sm", scale=1, min_width=70, variant="stop")
                    with gr.Row():
                        p_name = gr.Textbox(show_label=False, placeholder="save current chain as…", scale=3)
                        p_save = gr.Button("Save", size="sm", scale=1, min_width=70)
                    p_notes = gr.Textbox(label="Preset notes", lines=1, placeholder="optional")
                    p_status = gr.Markdown(elem_classes="status")

        # =================================================================== Library
        with gr.Tab("Library", id="library"):
            l_selected = gr.State(None)
            l_names = gr.State(_render_names())
            l_table = gr.Dataframe(headers=["label", "when", "seconds", "chain", "notes"], datatype=["str", "str", "number", "str", "str"],
                                   value=_renders_rows(), interactive=False, wrap=True, column_widths=["26%", "12%", "9%", "33%", "20%"])
            with gr.Row():
                with gr.Column(scale=6):
                    l_play = gr.Audio(label="Selected render", type="filepath")
                with gr.Column(scale=4):
                    l_notes = gr.Textbox(label="Notes", lines=3)
                    with gr.Row():
                        l_save_notes = gr.Button("Save notes")
                        l_delete = gr.Button("Delete render", variant="stop")

    # ---- wiring (quiet = no progress badge for instant, silent updates)
    quiet = {"show_progress": "hidden"}
    rec_save.click(save_take, [rec, rec_name], [rec_status, c_source, e_input])
    v_make.click(make_voice, [v_name, v_text, v_kokoro, v_speed], [v_status, c_voice, e_input])
    v_import.click(import_voice, [v_upload, v_name], [v_status, c_voice, e_input])
    c_voice.change(preview_voice, c_voice, v_play, **quiet)
    for trigger in (c_source.change, c_steps.change, c_model.change):
        trigger(_estimate, [c_source, c_steps, c_model], c_estimate, **quiet)
    c_go.click(convert, [c_source, c_voice, c_model, c_steps, c_cfg, c_keep, c_autof0, c_semi, c_v2_style, c_v2_intel, c_v2_sim, c_label],
               [c_out, c_ab, c_status, l_table, l_names, e_input])

    e_add.click(add_effect, [e_pick, chain_state], [chain_state], **quiet)
    chain_state.change(lambda chain: json.dumps(chain, indent=2), chain_state, e_json, **quiet)
    e_json_apply.click(replace_chain_json, [e_json, chain_state], [chain_state], **quiet)
    e_run.click(run_chain, [e_input, chain_state, e_label], [e_out, e_status, l_table, l_names, e_input])
    p_save.click(save_preset, [p_name, chain_state, p_notes], [p_status, p_list, p_name], **quiet)
    p_load.click(load_preset, p_list, chain_state, **quiet)
    p_delete.click(delete_preset, p_list, p_list, **quiet)

    l_table.select(select_render, [l_names], [l_selected, l_play, l_notes], **quiet)
    l_save_notes.click(save_notes, [l_selected, l_notes], [l_table, l_names], **quiet)
    l_delete.click(delete_render, [l_selected], [l_selected, l_play, l_table, l_names, e_input], **quiet)

    # keep every list current when the app opens or a tab is opened
    def refresh_all():
        return _sources(), _voices(), _audio_choices(), _presets(), _renders_rows(), _render_names()
    refresh_outputs = [c_source, c_voice, e_input, p_list, l_table, l_names]
    demo.load(refresh_all, None, refresh_outputs, **quiet).then(_estimate, [c_source, c_steps, c_model], c_estimate, **quiet)
    tabs.select(refresh_all, None, refresh_outputs, **quiet)


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="127.0.0.1", server_port=int(os.environ.get("PORT", "7860")),
                                                    show_api=os.environ.get("VOICE_LAB_SHOW_API") == "1", inbrowser=False, share=False)
