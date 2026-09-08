"""Voice Lab server: the single-page app plus a small JSON API over the library and the models.

    python app/server.py            (or scripts/run.sh)   ->   http://localhost:7860

Routes:  GET  /api/library                      voices and clips with their metadata
         POST /api/originals                    save a take (wav upload, name, type)         PUT /api/originals/{name}  replace after a crop
         POST /api/convert                      start a voice conversion job on the uploaded take; GET /api/jobs/{id} for progress
         POST /api/augmented                    save a render made in the browser (wav upload, name, type, effects)
         POST /api/voices                       synthesise a reference voice with Kokoro
         GET  /api/export/{kind}/{name}.{fmt}   deliver a clip as opus, mp3 or wav
         /clips/{kind}/{name}.wav               the audio files; /  the page
"""
from __future__ import annotations

import contextlib
import multiprocessing
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
os.environ["PYTHONPATH"] = f"{APP_DIR}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"   # the worker process imports from here too
import jobs  # noqa: E402
import library  # noqa: E402
from audio import duration, ensure_ffmpeg, load, peak_normalize  # noqa: E402
from tts import synthesize  # noqa: E402

ensure_ffmpeg()
STATIC = APP_DIR / "static"
# One long-lived worker process runs the models: Seed-VC's Python-heavy stages would otherwise starve the event loop.
_pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
# Measured on this laptop (oneDNN on, 15 steps): v1's F0 model ~11.5 s of compute per second of audio, v2 with its
# accent-and-emotion stage ~15 s/s. The worker's first job of each model also imports torch and loads the checkpoints
# (~35 s for v1 measured through the API). The page reads these too.
RATES = {"v1": {"rate": 11.5, "cold": 35.0}, "v2": {"rate": 15.0, "cold": 45.0}}
_warm = {"v1": False, "v2": False}
_jobs: dict[str, dict] = {}
Upload = Annotated[UploadFile, File()]

app = FastAPI(title="Voice Lab")


def _public(clip: dict) -> dict:
    return clip | {"url": f"/clips/{clip['kind']}/{clip['name']}.wav"}


@contextlib.contextmanager
def _uploaded(upload: UploadFile, keep: bool = False):
    """The upload as a temp wav path for the block; `keep` leaves the file for a worker that finishes later."""
    fd, path = tempfile.mkstemp(prefix="lab_", suffix=".wav")
    with os.fdopen(fd, "wb") as out:
        shutil.copyfileobj(upload.file, out)
    try:
        yield path
    finally:
        if not keep:
            Path(path).unlink(missing_ok=True)


def _estimate(seconds: float, mode: str, steps: int) -> float:
    return seconds * RATES[mode]["rate"] * int(steps) / 15.0 + (0.0 if _warm[mode] else RATES[mode]["cold"])


@app.get("/api/library")
def api_library():
    return {"voices": [_public(c) for c in library.list_clips("voice")],
            "clips": [_public(c) for kind in ("original", "augmented") for c in library.list_clips(kind)],
            "rates": RATES, "warm": _warm}


@app.post("/api/originals")
def api_original(file: Upload, name: Annotated[str, Form()] = "", type: Annotated[str, Form()] = "Voice"):
    with _uploaded(file) as path:
        return _public(library.clip("original", library.add_original(path, name, {"type": type})))


@app.put("/api/originals/{name}")
def api_original_update(name: str, file: Upload):
    if not library.clip("original", name):
        raise HTTPException(404, "no such original")
    with _uploaded(file) as path:
        library.update_original(name, path)
    return _public(library.clip("original", name))


@app.post("/api/convert")
def api_convert(file: Upload, voice: Annotated[str, Form()], mode: Annotated[str, Form()] = "v1", steps: Annotated[int, Form()] = 15,
                pitch: Annotated[int, Form()] = 0, name: Annotated[str, Form()] = "", type: Annotated[str, Form()] = "Voice",
                source: Annotated[str, Form()] = ""):
    if voice not in library.list_voices() or mode not in RATES:
        raise HTTPException(400, "no such voice or mode")
    with _uploaded(file, keep=True) as in_path:
        audio, sr = load(in_path)
    for stale in [k for k, j in _jobs.items() if j["status"] != "running" and time.time() - j["started"] > 3600]:
        _jobs.pop(stale)
    estimate = _estimate(duration(audio, sr), mode, steps)
    job = {"id": uuid.uuid4().hex[:8], "status": "running", "started": time.time(), "estimate": estimate, "clip": None, "error": None}
    _jobs[job["id"]] = job
    label = (name or "").strip()
    label = f"{label} · {voice}" if label else f"take · {voice}"
    out_path = in_path.replace(".wav", "-out.wav")

    def work():
        try:
            stats = _pool.submit(jobs.convert, in_path, out_path, voice, mode, int(steps), int(pitch)).result()   # blocks this thread only
            _warm[mode] = True
            out, out_sr = load(out_path)
            clip_name = library.save_augmented(out, out_sr, {
                "label": label, "type": type, "voice": voice, "mode": "Timbre" if mode == "v1" else "Emotion", "steps": int(steps),
                "pitch": int(pitch), "input": source,
                "stats": {"compute_s": round(time.time() - job["started"]), "f0_in": stats["f0_in"], "f0_out": stats["f0_out"]}}, label=label)
            job["clip"] = _public(library.clip("augmented", clip_name))
            job["status"] = "done"
        except Exception as e:  # reported to the page
            traceback.print_exc()
            job["error"] = str(e)
            job["status"] = "failed"
        finally:
            for path in (in_path, out_path):
                Path(path).unlink(missing_ok=True)

    threading.Thread(target=work, daemon=True).start()
    return {"id": job["id"], "estimate": estimate}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    elapsed = time.time() - job["started"]
    return {"status": job["status"], "progress": 1.0 if job["status"] == "done" else min(0.97, elapsed / max(job["estimate"], 1.0)),
            "eta": max(0.0, job["estimate"] - elapsed), "clip": job["clip"], "error": job["error"]}


@app.post("/api/augmented")
def api_augmented(file: Upload, name: Annotated[str, Form()] = "", type: Annotated[str, Form()] = "Voice",
                  effects: Annotated[str, Form()] = "", source: Annotated[str, Form()] = ""):
    with _uploaded(file) as path:
        audio, sr = load(path)
    label = (name or "").strip() or f"render · {effects or 'dry'}"
    clip_name = library.save_augmented(audio, sr, {"label": label, "type": type, "effects": effects, "input": source}, label=label)
    return _public(library.clip("augmented", clip_name))


@app.post("/api/voices")
def api_voice(name: Annotated[str, Form()], text: Annotated[str, Form()], kokoro: Annotated[str, Form()] = "af_bella",
              speed: Annotated[float, Form()] = 0.9):
    audio, sr = synthesize(text, kokoro, speed)
    vname = library.add_voice(name, peak_normalize(audio), sr, {"text": text, "kokoro_voice": kokoro, "speed": speed})
    return _public(library.clip("voice", vname))


@app.get("/api/export/{kind}/{name}.{fmt}")
def api_export(kind: str, name: str, fmt: str):
    if fmt not in library.EXPORT_FORMATS or not library.clip(kind, name):
        raise HTTPException(404, "no such clip or format")
    path = library.export_clip(kind, name, fmt)
    return FileResponse(path, filename=os.path.basename(path))


for kind, folder in library.FOLDERS.items():
    app.mount(f"/clips/{kind}", StaticFiles(directory=folder), name=kind)
app.mount("/", StaticFiles(directory=STATIC, html=True), name="page")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "7860")), log_level="warning")
