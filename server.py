"""
Claude DJ — FastAPI streaming server.

Endpoints:
  POST /api/analyze          start background track analysis
  GET  /api/analyze/{job_id} poll analysis progress
  POST /api/plan             call Claude, build MixScript, load audio, create session
  GET  /api/status/{id}      current playback bar / buffer depth
  WS   /ws/stream/{id}       stream float32 PCM chunks, accept seek messages
  GET  /api/script/{id}      return the mix script JSON for a session

Static frontend (dist/) is served at / when present.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

# Load .env from the project directory so ANTHROPIC_API_KEY can be set there
_dotenv_path = Path(__file__).parent / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv_path)
    except ImportError:
        # python-dotenv not installed — parse manually
        for line in _dotenv_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from audio_queue import ChunkScheduler
from executor import _stem_dir_for_track, bars_to_ms, load_track, time_stretch
from mix_director import direct_mix
from normalizer import normalize
from pydub import AudioSegment
from schema import MixScript

app = FastAPI(title="Claude DJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}


# ── In-process state (single-user local tool) ──────────────────────────────────
_analyze_jobs: dict[str, dict] = {}  # job_id → {status, progress, total, analyses, error}
_sessions:     dict[str, dict] = {}  # session_id → {script, scheduler, ref_bpm, tracks}
_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dj-bg")


# ─── JSON sanitizer ───────────────────────────────────────────────────────────

def _sanitize(obj: object) -> object:
    """
    Recursively replace non-JSON-compliant values:
    - float NaN / Inf  → None
    - numpy scalar types → Python native types
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    try:
        if isinstance(obj, np.floating):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return _sanitize(obj.tolist())
    except Exception:
        pass
    return obj


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_audio_for_script(script: MixScript) -> tuple[dict, dict, float]:
    """Load, trim, and time-stretch all tracks + stems. Returns (loaded, stem_layers, ref_bpm)."""
    ref_bpm = float(np.median([t.bpm for t in script.tracks]))
    loaded: dict[str, AudioSegment] = {}

    for t in script.tracks:
        seg = load_track(t.path)
        first_db_ms = int(t.first_downbeat_s * 1000)
        if first_db_ms > 0:
            seg = seg[first_db_ms:]
        seg = time_stretch(seg, t.bpm, ref_bpm)
        loaded[t.id] = seg

    target_rate = next(iter(loaded.values())).frame_rate
    for tid in loaded:
        if loaded[tid].frame_rate != target_rate:
            loaded[tid] = loaded[tid].set_frame_rate(target_rate)

    stem_layers: dict[tuple[str, str], AudioSegment] = {}
    for t in script.tracks:
        stem_dir = _stem_dir_for_track(t.id, script)
        for stem_name in ("drums", "bass", "vocals", "other"):
            path = stem_dir / f"{stem_name}.wav"
            if path.exists():
                seg = AudioSegment.from_wav(str(path))
                seg = time_stretch(seg, t.bpm, ref_bpm)
                if seg.frame_rate != target_rate:
                    seg = seg.set_frame_rate(target_rate)
                stem_layers[(t.id, stem_name)] = seg

    return loaded, stem_layers, ref_bpm


# ─── Analysis ─────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    tracks_dir: str
    no_stems: bool = False


async def _run_analyze(job_id: str, tracks_dir: str, no_stems: bool) -> None:
    try:
        from analyze import analyze_track

        td = Path(tracks_dir).resolve()
        if not td.is_dir():
            _analyze_jobs[job_id].update(status="error", error=f"Not a directory: {tracks_dir}")
            return

        audio_exts = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
        track_paths = sorted(
            str(p) for p in td.iterdir()
            if p.suffix.lower() in audio_exts
        )
        if not track_paths:
            _analyze_jobs[job_id].update(status="error", error="No audio files found")
            return

        _analyze_jobs[job_id]["total"] = len(track_paths)
        loop = asyncio.get_running_loop()
        analyses = []
        for i, path in enumerate(track_paths):
            _analyze_jobs[job_id]["progress"] = i
            analysis = await loop.run_in_executor(
                _bg_executor, analyze_track, path, f"T{i + 1}", no_stems
            )
            analyses.append(_sanitize(analysis.to_dict()))
            _analyze_jobs[job_id]["analyses"] = analyses[:]

        _analyze_jobs[job_id].update(status="done", progress=len(track_paths))
    except Exception as exc:
        _analyze_jobs[job_id].update(status="error", error=str(exc))


@app.post("/api/analyze")
async def start_analyze(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _analyze_jobs[job_id] = {
        "status": "running", "progress": 0, "total": 0, "analyses": [], "error": None,
    }
    background_tasks.add_task(_run_analyze, job_id, req.tracks_dir, req.no_stems)
    return {"job_id": job_id}


@app.get("/api/analyze/{job_id}")
async def get_analyze_status(job_id: str):
    job = _analyze_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return {
        "status":   job["status"],
        "progress": job["progress"],
        "total":    job["total"],
        "analyses": job["analyses"] if job["status"] == "done" else [],
        "error":    job["error"],
    }


# ─── Planning ─────────────────────────────────────────────────────────────────

class PlanRequest(BaseModel):
    job_id: str
    model: str = "claude-sonnet-4-6"
    min_minutes: Optional[int] = None


@app.post("/api/plan")
async def plan_mix(req: PlanRequest):
    job = _analyze_jobs.get(req.job_id)
    if not job or job["status"] != "done":
        return JSONResponse({"error": "analysis not ready"}, status_code=400)

    from analyze import _dict_to_analysis

    analyses = [_dict_to_analysis(d) for d in job["analyses"]]
    loop = asyncio.get_running_loop()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY not set. Add it to claude-dj/.env or export it in your shell."},
            status_code=503,
        )

    # Claude call (blocking) → run in thread pool
    try:
        script: MixScript = await loop.run_in_executor(
            _bg_executor, direct_mix, analyses, req.model, req.min_minutes,
        )
    except TypeError as e:
        if "api_key" in str(e) or "authentication" in str(e).lower():
            return JSONResponse({"error": f"Anthropic auth error: {e}"}, status_code=503)
        raise
    script = normalize(script)

    # Load audio (blocking, potentially slow for large files)
    loaded, stem_layers, ref_bpm = await loop.run_in_executor(
        _bg_executor, _load_audio_for_script, script,
    )

    session_id = str(uuid.uuid4())
    scheduler  = ChunkScheduler(script, loaded, stem_layers, ref_bpm)
    await scheduler.start()

    _sessions[session_id] = {
        "script":    script,
        "scheduler": scheduler,
        "ref_bpm":   ref_bpm,
        "tracks":    [dataclasses.asdict(t) for t in script.tracks],
    }

    return _sanitize({
        "session_id": session_id,
        "script":     dataclasses.asdict(script),
        "ref_bpm":    ref_bpm,
    })


# ─── Status ───────────────────────────────────────────────────────────────────

@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    sess = _sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    sched: ChunkScheduler = sess["scheduler"]
    return {
        "current_bar":       sched.current_bar,
        "buffer_depth_bars": sched.buffer_depth_bars,
        "ref_bpm":           sess["ref_bpm"],
        "tracks":            sess["tracks"],
    }


@app.get("/api/script/{session_id}")
async def get_script(session_id: str):
    sess = _sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return _sanitize(dataclasses.asdict(sess["script"]))


# ─── Stream ───────────────────────────────────────────────────────────────────

@app.websocket("/ws/stream/{session_id}")
async def stream_audio(ws: WebSocket, session_id: str):
    await ws.accept()
    sess = _sessions.get(session_id)
    if not sess:
        await ws.close(code=4404)
        return

    sched: ChunkScheduler = sess["scheduler"]

    async def _handle_control() -> None:
        """Read control messages (seek, stop) from the client."""
        try:
            while True:
                text = await ws.receive_text()
                msg  = json.loads(text)
                if msg.get("action") == "seek" and "bar" in msg:
                    sched.seek(int(msg["bar"]))
        except (WebSocketDisconnect, Exception):
            pass

    control_task = asyncio.create_task(_handle_control())

    try:
        while True:
            chunk_bytes = await sched.get_chunk()
            sched.advance()
            await ws.send_bytes(chunk_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[stream/{session_id}] error: {exc}")
    finally:
        control_task.cancel()


# ─── Cleanup ──────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def _shutdown() -> None:
    for sess in _sessions.values():
        await sess["scheduler"].stop()


# ─── Static frontend ──────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")
