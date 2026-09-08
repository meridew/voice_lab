"""Voice Lab server: the single-page app plus a small JSON API over the library and the models.

    python app/server.py            (or scripts/run.sh)   ->   http://localhost:7860

Routes:  GET  /api/library                      voices and clips with their metadata
         POST /api/originals                    save a take (wav upload, name, type, mic)    PUT /api/originals/{name}  replace after a crop
         POST /api/convert                      start a voice conversion job on the uploaded take; GET /api/jobs/{id} for progress
         POST /api/augmented                    save a render made in the browser (wav upload, name, type, effects)
         POST /api/voices                       synthesise a reference voice with Kokoro
         GET  /api/export/{kind}/{name}.{fmt}   deliver a clip as opus, mp3 or wav
         /clips/{kind}/{name}.wav               the audio files; /  the page
"""
from __future__ import annotations

import contextlib
import json
import math
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

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
os.environ["PYTHONPATH"] = f"{APP_DIR}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"   # the worker process imports from here too
import jobs  # noqa: E402
import library  # noqa: E402
import tts  # noqa: E402
from audio import duration, ensure_ffmpeg, load, peak_normalize  # noqa: E402

ensure_ffmpeg()
STATIC = APP_DIR / "static"
# One long-lived worker process runs the models: Seed-VC's Python-heavy stages would otherwise starve the event loop.
_pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
# Conversion time = fixed + per_step_second x steps x (take seconds + reference voice seconds), because every diffusion
# step covers the reference alongside the take, plus a cold-load allowance the startup warm-up normally hides. These
# priors were fitted on this laptop; every finished conversion is added to the fit, so the estimate keeps improving.
PRIORS = {"v1": {"fixed": 3.0, "per_step_second": 0.1, "cold": 25.0}, "v2": {"fixed": 8.0, "per_step_second": 0.15, "cold": 16.0}}
RATES = {mode: dict(r) for mode, r in PRIORS.items()}
_samples: dict[str, list[tuple[float, float]]] = {"v1": [], "v2": []}       # (steps x seconds, measured compute seconds), warm runs only
_warm = {"v1": False, "v2": False}
_jobs: dict[str, dict] = {}
Upload = Annotated[UploadFile, File()]


def _refit(mode: str) -> None:
    """Least squares over the recorded runs, anchored to the prior as if it were three runs, never below zero."""
    prior = PRIORS[mode]
    xs = [0.0, 200.0] * 3 + [x for x, _ in _samples[mode]]
    ys = [prior["fixed"], prior["fixed"] + prior["per_step_second"] * 200.0] * 3 + [y for _, y in _samples[mode]]
    (fixed, per), *_ = np.linalg.lstsq(np.column_stack([np.ones(len(xs)), xs]), np.array(ys), rcond=None)
    RATES[mode].update(fixed=round(max(0.0, float(fixed)), 2), per_step_second=round(max(0.0, float(per)), 4))


def _remember(mode: str, stats: dict) -> None:
    if not stats.get("cold"):
        _samples[mode].append((stats["steps"] * (stats["take_s"] + stats["voice_s"]), stats["compute_s"]))
        _refit(mode)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    for clip in library.list_clips("augmented"):                              # the fit starts from every past run on disk
        meta = library.meta("augmented", clip["name"])
        if clip.get("mode") in MODES and {"compute_s", "take_s", "voice_s", "steps"} <= set(meta.get("stats", {})):
            _remember(MODES[clip["mode"]], meta["stats"])
    if os.environ.get("VOICE_LAB_WARM", "1") != "0":
        _pool.submit(jobs.warm).add_done_callback(lambda done: _warm.__setitem__("v1", done.exception() is None))
    yield
    _pool.shutdown(cancel_futures=True)


MODES = {"Timbre": "v1", "Emotion": "v2"}
MODE_NAME = {v: k for k, v in MODES.items()}


app = FastAPI(title="Voice Lab", lifespan=lifespan)


@app.middleware("http")
async def no_stale_page(request, call_next):
    """The page's files always revalidate (ETags make that cheap); otherwise browsers keep old modules for minutes after an edit."""
    response = await call_next(request)
    if not request.url.path.startswith("/clips/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


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


def _estimate(take_s: float, voice_s: float, mode: str, steps: int) -> float:
    r = RATES[mode]
    return r["fixed"] + r["per_step_second"] * int(steps) * (take_s + voice_s) + (0.0 if _warm[mode] else r["cold"])


@app.get("/api/library")
def api_library():
    return {"voices": [_public(c) for c in library.list_clips("voice")],
            "clips": [_public(c) for kind in ("original", "augmented") for c in library.list_clips(kind)],
            "rates": RATES, "warm": _warm, "kokoro": tts.KOKORO_VOICES}


@app.delete("/api/clips/{kind}/{name}")
def api_delete(kind: str, name: str):
    if kind not in library.FOLDERS or not library.clip(kind, name):
        raise HTTPException(404, "no such clip")
    library.delete_clip(kind, name)
    return {"deleted": f"{kind}:{name}"}


@app.post("/api/originals")
def api_original(file: Upload, name: Annotated[str, Form()] = "", type: Annotated[str, Form()] = "Voice", mic: Annotated[str, Form()] = ""):
    meta = {"type": type}
    with contextlib.suppress(ValueError):
        if mic:
            meta["mic"] = json.loads(mic)                                          # the device and processing the take was made with
    with _uploaded(file) as path:
        return _public(library.clip("original", library.add_original(path, name, meta)))


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
    reference = library.clip("voice", voice)
    if not reference or mode not in RATES:
        raise HTTPException(400, "no such voice or mode")
    with _uploaded(file, keep=True) as in_path:
        audio, sr = load(in_path)
    for stale in [k for k, j in _jobs.items() if j["status"] != "running" and time.time() - j["started"] > 3600]:
        _jobs.pop(stale)
    take_s, voice_s, cold = duration(audio, sr), reference["seconds"], not _warm[mode]
    estimate = _estimate(take_s, voice_s, mode, steps)
    job = {"id": uuid.uuid4().hex[:8], "status": "running", "started": time.time(), "estimate": estimate, "clip": None, "error": None}
    _jobs[job["id"]] = job
    label = (name or "").strip()
    label = f"{label} · {voice}" if label else f"take · {voice}"
    out_path = in_path.replace(".wav", "-out.wav")

    def work():
        try:
            result = _pool.submit(jobs.convert, in_path, out_path, voice, mode, int(steps), int(pitch)).result()   # blocks this thread only
            _warm[mode] = True
            out, out_sr = load(out_path)
            stats = {"compute_s": round(time.time() - job["started"], 1), "take_s": round(take_s, 2), "voice_s": round(voice_s, 2),
                     "steps": int(steps), "cold": cold, "f0_in": result["f0_in"], "f0_out": result["f0_out"]}
            clip_name = library.save_augmented(out, out_sr, {"label": label, "type": type, "voice": voice, "mode": MODE_NAME[mode],
                                                             "steps": int(steps), "pitch": int(pitch), "input": source, "stats": stats}, label=label)
            _remember(mode, stats)
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
    ratio = elapsed / max(job["estimate"], 1.0)
    # Linear to 90% at the estimate; past it the bar keeps creeping toward the end rather than stopping dead.
    progress = 1.0 if job["status"] == "done" else (0.9 * ratio if ratio < 1 else 0.9 + 0.1 * (1 - math.exp(-2 * (ratio - 1))))
    return {"status": job["status"], "progress": progress, "eta": max(0.0, job["estimate"] - elapsed), "clip": job["clip"], "error": job["error"]}


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
    audio, sr = tts.synthesize(text, kokoro, speed)
    vname = library.add_voice(name, peak_normalize(audio), sr, {"text": text, "kokoro_voice": kokoro, "speed": speed})
    return _public(library.clip("voice", vname))


@app.get("/api/export/{kind}/{name}.{fmt}")
def api_export(kind: str, name: str, fmt: str):
    if fmt not in library.EXPORT_FORMATS or not library.clip(kind, name):
        raise HTTPException(404, "no such clip or format")
    path, filename = library.export_clip(kind, name, fmt)
    return FileResponse(path, filename=filename, background=BackgroundTask(shutil.rmtree, os.path.dirname(path), ignore_errors=True))


for kind, folder in library.FOLDERS.items():
    app.mount(f"/clips/{kind}", StaticFiles(directory=folder), name=kind)
app.mount("/", StaticFiles(directory=STATIC, html=True), name="page")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "7860")), log_level="warning")
