"""
Claude DJ — FastAPI streaming server (routes only).

Endpoints:
  GET  /api/library              list library tracks
  POST /api/library/scan         start background folder scan
  GET  /api/library/scan/{id}    poll scan progress
  GET  /api/session/{id}         poll session loading state
  GET  /api/status/{id}          current bar + buffer depth
  GET  /api/script/{id}          mix script JSON
  WS   /ws/stream/{id}           float32 PCM chunks
  POST /api/dj/start             start auto-DJ session
  GET  /api/dj/{id}              poll DJ session state
  POST /api/dj/{id}/queue        add a track to the DJ queue
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
from pydub import AudioSegment
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

# Load .env
_dotenv_path = Path(__file__).parent / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv_path)
    except ImportError:
        for line in _dotenv_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from analyze import CACHE_DIR, analyze_track as _analyze_track, file_hash
from audio_queue import ChunkScheduler, MIX_END_SENTINEL
from dj_session import dj_worker
from library import Library
from schema import MixScript
from state import (
    AudioSession, AudioSessionStore, DjDeckB, DjSessionState, DjSessionStore,
    LibraryEntry, ScanJobStore,
)

app = FastAPI(title="Claude DJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────

_library     = Library(CACHE_DIR)
_audio_store = AudioSessionStore()
_dj_store    = DjSessionStore()
_scan_store  = ScanJobStore()
_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dj-bg")
_library.load()

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}


def get_library() -> Library:
    return _library


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sanitize(obj: object) -> object:
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


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


# ── Library ───────────────────────────────────────────────────────────────────

class LibraryScanRequest(BaseModel):
    folder: str


async def _run_scan(scan_id: str, folder: str) -> None:
    from datetime import datetime
    job = _scan_store.get(scan_id)
    try:
        td = Path(folder).resolve()
        if not td.is_dir():
            job.status = "error"
            job.error  = f"Not a directory: {folder}"
            return

        files = sorted(str(p) for p in td.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if not files:
            job.status = "error"
            job.error  = "No audio files found"
            return

        job.total = len(files)
        loop = asyncio.get_running_loop()
        known, new_count, skipped = 0, 0, 0

        for i, path in enumerate(files):
            job.progress = i
            try:
                h = await loop.run_in_executor(_bg_executor, file_hash, path)
                existing = _library.get(h)
                if existing:
                    existing.path = path
                    _library.upsert(h, existing)
                    known += 1
                    continue

                analysis = await loop.run_in_executor(
                    _bg_executor, _analyze_track, path, f"lib_{h[:8]}", True,
                )
                entry = LibraryEntry(
                    hash             = h,
                    path             = path,
                    title            = analysis.title,
                    artist           = analysis.artist,
                    bpm              = round(analysis.bpm, 1),
                    key_camelot      = analysis.key.camelot,
                    key_standard     = analysis.key.standard,
                    energy           = analysis.energy_overall,
                    duration_s       = round(analysis.duration_s, 1),
                    energy_curve     = analysis.energy_curve_per_bar,
                    cue_points       = [
                        {"name": c.name, "bar": c.bar, "type": c.type}
                        for c in analysis.cue_points
                    ],
                    first_downbeat_s = round(analysis.first_downbeat_s, 3),
                    analyzed_at      = datetime.utcnow().isoformat(),
                    loudness_dbfs    = analysis.loudness_dbfs,
                )
                _library.upsert(h, entry)
                new_count += 1
                job.new = new_count
            except Exception as exc:
                print(f"[scan] skipping {Path(path).name}: {exc}", flush=True)
                skipped += 1
                job.skipped = skipped

        job.status   = "done"
        job.progress = len(files)
        job.known    = known
        job.new      = new_count
    except Exception as exc:
        import traceback
        job.status = "error"
        job.error  = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


@app.post("/api/library/scan")
async def library_scan(req: LibraryScanRequest, background_tasks: BackgroundTasks):
    scan_id = str(uuid.uuid4())
    _scan_store.create(scan_id)
    background_tasks.add_task(_run_scan, scan_id, req.folder)
    return {"scan_id": scan_id}


@app.get("/api/library/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    job = _scan_store.get(scan_id)
    if not job:
        return JSONResponse({"error": "scan not found"}, status_code=404)
    return dataclasses.asdict(job)


@app.get("/api/library")
async def get_library_endpoint():
    tracks = [dataclasses.asdict(e) for e in _library.get_all()]
    return {"tracks": tracks, "total": len(tracks)}


# ── Session / Status / Script ─────────────────────────────────────────────────

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return {
        "status":        sess.status,
        "load_progress": sess.load_progress,
        "load_total":    sess.load_total,
        "ref_bpm":       sess.ref_bpm,
        "tracks":        sess.tracks,
        "error":         sess.error,
    }


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    sched = sess.scheduler
    if sched is None:
        return {"current_bar": 0, "buffer_depth_bars": 0,
                "ref_bpm": sess.ref_bpm, "status": sess.status}
    return {
        "current_bar":       sched.current_bar,
        "buffer_depth_bars": sched.buffer_depth_bars,
        "ref_bpm":           sess.ref_bpm,
        "tracks":            sess.tracks,
        "status":            sess.status,
    }


@app.get("/api/script/{session_id}")
async def get_script(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return _sanitize(dataclasses.asdict(sess.script))


# ── WebSocket stream ──────────────────────────────────────────────────────────

_SESSION_READY_TIMEOUT_S = 600


@app.websocket("/ws/stream/{session_id}")
async def stream_audio(ws: WebSocket, session_id: str):
    await ws.accept()
    sess = _audio_store.get(session_id)
    if not sess:
        await ws.close(code=4404)
        return

    waited = 0.0
    while sess.status == "loading":
        await asyncio.sleep(0.5)
        waited += 0.5
        await ws.send_text(json.dumps({
            "type": "loading",
            "progress": sess.load_progress,
            "total":    sess.load_total,
        }))
        if waited >= _SESSION_READY_TIMEOUT_S:
            await ws.send_text(json.dumps({"type": "error", "msg": "audio loading timed out"}))
            await ws.close()
            return

    if sess.status == "error":
        await ws.send_text(json.dumps({"type": "error", "msg": sess.error or "load failed"}))
        await ws.close()
        return

    sched: ChunkScheduler = sess.scheduler

    async def _handle_control() -> None:
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
            if chunk_bytes == MIX_END_SENTINEL:
                await ws.send_text(json.dumps({"type": "end"}))
                break
            sched.advance()
            await ws.send_bytes(chunk_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[stream/{session_id}] error: {exc}")
    finally:
        control_task.cancel()


# ── Auto-DJ ───────────────────────────────────────────────────────────────────

class DjStartRequest(BaseModel):
    pool:            list[str] = []
    queue:           list[str] = []
    let_claude_pick: bool      = True
    model:           str       = "claude-sonnet-4-6"


@app.post("/api/dj/start")
async def dj_start(req: DjStartRequest, background_tasks: BackgroundTasks):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse({"error": "ANTHROPIC_API_KEY not set."}, status_code=503)

    pool  = [h for v in req.pool  if (h := _library.resolve(v))]
    queue = [h for v in req.queue if (h := _library.resolve(v))]
    if not pool and not queue:
        pool = [e.hash for e in _library.get_all()]

    dj_id = str(uuid.uuid4())
    state = DjSessionState(
        dj_id          = dj_id,
        status         = "starting",
        model          = req.model,
        let_claude_pick = req.let_claude_pick,
        pool           = pool,
        queue          = queue,
        deck_b         = DjDeckB(status="starting", title="…"),
    )
    _dj_store.create(dj_id, state)
    background_tasks.add_task(dj_worker, dj_id, _dj_store, _audio_store, _library)
    return {"dj_id": dj_id}


@app.get("/api/dj/{dj_id}")
async def get_dj_state(dj_id: str):
    state = _dj_store.get(dj_id)
    if not state:
        return JSONResponse({"error": "dj session not found"}, status_code=404)

    session_id     = state.session_id
    script_summary = None
    if session_id:
        audio_sess = _audio_store.get(session_id)
        if audio_sess and audio_sess.script:
            script_summary = _sanitize(dataclasses.asdict(audio_sess.script))

    return _sanitize({
        "status":     state.status,
        "session_id": session_id,
        "deck_a":     dataclasses.asdict(state.deck_a) if state.deck_a else None,
        "deck_b":     dataclasses.asdict(state.deck_b) if state.deck_b else None,
        "history":    state.history,
        "queue":      state.queue,
        "ref_bpm":    state.ref_bpm,
        "script":     script_summary,
        "error":      state.error,
    })


@app.get("/api/dj/{dj_id}/log")
async def get_dj_log(dj_id: str):
    state = _dj_store.get(dj_id)
    if not state:
        return JSONResponse({"error": "dj session not found"}, status_code=404)
    return _sanitize({"log": [dataclasses.asdict(e) for e in state.transition_log]})


@app.post("/api/dj/{dj_id}/queue")
async def dj_enqueue(dj_id: str, body: dict):
    state = _dj_store.get(dj_id)
    if not state:
        return JSONResponse({"error": "dj session not found"}, status_code=404)
    h = body.get("hash") or body.get("path")
    resolved = _library.resolve(h) if h else None
    if not resolved:
        return JSONResponse({"error": "track not in library"}, status_code=400)
    state.queue.append(resolved)
    return {"queued": resolved, "queue_length": len(state.queue)}


# ── Shutdown ──────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def _shutdown() -> None:
    for sess in _audio_store.values():
        if sess.scheduler is not None:
            await sess.scheduler.stop()


# ── Static frontend ───────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")
