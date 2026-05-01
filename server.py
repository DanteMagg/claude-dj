"""
Claude DJ — FastAPI streaming server.

Endpoints:
  POST /api/analyze            start background track analysis
  GET  /api/analyze/{job_id}   poll analysis progress
  POST /api/plan               call Claude, return script + session_id immediately.
                               Audio loading happens in background.
  GET  /api/session/{id}       poll session loading status (loading/ready/error)
  GET  /api/status/{id}        current playback bar / buffer depth (ready sessions only)
  WS   /ws/stream/{id}         stream float32 PCM chunks; waits for session to be ready
  GET  /api/script/{id}        return the mix script JSON for a session

The split between /api/plan and session loading is intentional:
  - /api/plan returns within seconds (just the Claude call).
  - The frontend can show the script/transition log immediately.
  - Audio loading (time-stretch, stem load) runs in the background.
  - The WebSocket endpoint waits for "ready" before streaming starts.
  - The client polls /api/session/{id} to show a progress indicator.

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
from mix_director import direct_mix, select_next_track
from normalizer import normalize
from pydub import AudioSegment
from schema import (
    BarGrid, CuePoint, KeyInfo, MixAction, MixScript, MixTrackRef,
    StemPaths, TrackAnalysis,
)

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
_scan_jobs:    dict[str, dict] = {}  # scan_id  → {status, progress, total, known, new, error}
_dj_sessions:  dict[str, dict] = {}  # dj_id   → deck_a/b, queue, session_id, …
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


async def _load_session_audio(session_id: str) -> None:
    """Background task: load + time-stretch tracks/stems, then mark session ready."""
    sess = _sessions[session_id]
    script: MixScript = sess["script"]
    n = len(script.tracks)
    try:
        loop = asyncio.get_running_loop()

        def _load_with_progress():
            ref_bpm = float(np.median([t.bpm for t in script.tracks]))
            loaded: dict[str, AudioSegment] = {}
            for i, t in enumerate(script.tracks):
                sess["load_progress"] = i
                seg = load_track(t.path)
                first_db_ms = int(t.first_downbeat_s * 1000)
                if first_db_ms > 0:
                    seg = seg[first_db_ms:]
                loaded[t.id] = time_stretch(seg, t.bpm, ref_bpm)

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

        loaded, stem_layers, ref_bpm = await loop.run_in_executor(_bg_executor, _load_with_progress)

        scheduler = ChunkScheduler(script, loaded, stem_layers, ref_bpm)
        await scheduler.start()

        sess.update(
            status="ready",
            scheduler=scheduler,
            ref_bpm=ref_bpm,
            load_progress=n,
            load_total=n,
        )
    except Exception as exc:
        sess.update(status="error", error=str(exc))


@app.post("/api/plan")
async def plan_mix(req: PlanRequest, background_tasks: BackgroundTasks):
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

    # Claude call only — this is the fast part (~5s)
    try:
        script: MixScript = await loop.run_in_executor(
            _bg_executor, direct_mix, analyses, req.model, req.min_minutes,
        )
    except TypeError as e:
        if "api_key" in str(e) or "authentication" in str(e).lower():
            return JSONResponse({"error": f"Anthropic auth error: {e}"}, status_code=503)
        raise
    script = normalize(script)

    # Register session immediately (status=loading) so the frontend can render the
    # script and show a progress bar while audio loads in the background.
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "status":        "loading",
        "script":        script,
        "scheduler":     None,
        "ref_bpm":       float(np.median([t.bpm for t in script.tracks])),
        "tracks":        [dataclasses.asdict(t) for t in script.tracks],
        "load_progress": 0,
        "load_total":    len(script.tracks),
        "error":         None,
    }

    # Audio loading happens in background — client polls /api/session/{id}
    background_tasks.add_task(_load_session_audio, session_id)

    return _sanitize({
        "session_id": session_id,
        "status":     "loading",
        "script":     dataclasses.asdict(script),
        "ref_bpm":    _sessions[session_id]["ref_bpm"],
        "load_total": len(script.tracks),
    })


# ─── Session / Status ─────────────────────────────────────────────────────────

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Poll session loading state. Frontend should call this until status == 'ready'."""
    sess = _sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return {
        "status":        sess["status"],
        "load_progress": sess.get("load_progress", 0),
        "load_total":    sess.get("load_total", 0),
        "ref_bpm":       sess["ref_bpm"],
        "tracks":        sess["tracks"],
        "error":         sess.get("error"),
    }


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """Playback position + buffer depth (only meaningful once session is ready)."""
    sess = _sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    sched: Optional[ChunkScheduler] = sess.get("scheduler")
    if sched is None:
        return {"current_bar": 0, "buffer_depth_bars": 0,
                "ref_bpm": sess["ref_bpm"], "status": sess["status"]}
    return {
        "current_bar":       sched.current_bar,
        "buffer_depth_bars": sched.buffer_depth_bars,
        "ref_bpm":           sess["ref_bpm"],
        "tracks":            sess["tracks"],
        "status":            sess["status"],
    }


@app.get("/api/script/{session_id}")
async def get_script(session_id: str):
    sess = _sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return _sanitize(dataclasses.asdict(sess["script"]))


# ─── Stream ───────────────────────────────────────────────────────────────────

from audio_queue import MIX_END_SENTINEL

_SESSION_READY_TIMEOUT_S = 600  # wait up to 10 minutes for audio to load


@app.websocket("/ws/stream/{session_id}")
async def stream_audio(ws: WebSocket, session_id: str):
    await ws.accept()
    sess = _sessions.get(session_id)
    if not sess:
        await ws.close(code=4404)
        return

    # Wait for audio loading to complete before streaming starts.
    # The client already knows the script; this delay only blocks audio playback.
    waited = 0.0
    while sess.get("status") == "loading":
        await asyncio.sleep(0.5)
        waited += 0.5
        progress = sess.get("load_progress", 0)
        total    = sess.get("load_total", 1)
        await ws.send_text(json.dumps({
            "type": "loading", "progress": progress, "total": total,
        }))
        if waited >= _SESSION_READY_TIMEOUT_S:
            await ws.send_text(json.dumps({"type": "error", "msg": "audio loading timed out"}))
            await ws.close()
            return

    if sess.get("status") == "error":
        await ws.send_text(json.dumps({"type": "error", "msg": sess.get("error", "load failed")}))
        await ws.close()
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
            if chunk_bytes == MIX_END_SENTINEL:
                # Signal client that the mix is complete, then close cleanly
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


# ─── Persistent Library ───────────────────────────────────────────────────────

from analyze import CACHE_DIR, file_hash, analyze_track as _analyze_track

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
_LIBRARY_FILE = CACHE_DIR / "library.json"

# hash16 → {path, title, artist, bpm, key_camelot, key_standard, energy,
#            duration_s, energy_curve, cue_points, first_downbeat_s, analyzed_at}
_library: dict[str, dict] = {}


def _load_library() -> None:
    global _library
    if _LIBRARY_FILE.exists():
        try:
            _library = json.loads(_LIBRARY_FILE.read_text())
        except Exception:
            _library = {}


def _save_library() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _LIBRARY_FILE.write_text(json.dumps(_library, indent=2))


def _entry_from_analysis(analysis: TrackAnalysis, h: str) -> dict:
    from datetime import datetime
    return {
        "hash": h,
        "path": analysis.file,
        "title": analysis.title,
        "artist": analysis.artist,
        "bpm": round(analysis.bpm, 1),
        "key_camelot": analysis.key.camelot,
        "key_standard": analysis.key.standard,
        "energy": analysis.energy_overall,
        "duration_s": round(analysis.duration_s, 1),
        "energy_curve": analysis.energy_curve_per_bar,
        "cue_points": [{"name": c.name, "bar": c.bar, "type": c.type} for c in analysis.cue_points],
        "first_downbeat_s": round(analysis.first_downbeat_s, 3),
        "analyzed_at": datetime.utcnow().isoformat(),
    }


def _analysis_from_entry(entry: dict, track_id: str) -> TrackAnalysis:
    """Build a lightweight TrackAnalysis from persisted library metadata."""
    key_std = entry.get("key_standard", "C major")
    tonic   = key_std.split()[0]
    mode    = "minor" if key_std.endswith("m") or "minor" in key_std else "major"
    bpm     = float(entry.get("bpm", 128.0))
    dur     = float(entry.get("duration_s", 180.0))
    n_bars  = max(1, int(dur * bpm / 240))
    return TrackAnalysis(
        id=track_id,
        title=entry.get("title", ""),
        artist=entry.get("artist", ""),
        file=entry.get("path", ""),
        duration_s=dur,
        bpm=bpm,
        first_downbeat_s=float(entry.get("first_downbeat_s", 0.0)),
        key=KeyInfo(
            camelot=entry.get("key_camelot", "8B"),
            standard=key_std,
            mode=mode,
            tonic=tonic,
        ),
        energy_overall=int(entry.get("energy", 5)),
        loudness_dbfs=-14.0,
        bar_grid=BarGrid(n_bars=n_bars, beats_per_bar=4),
        energy_curve_per_bar=entry.get("energy_curve", ""),
        sections=[],
        cue_points=[
            CuePoint(name=c["name"], bar=c["bar"], type=c.get("type", "phrase_start"))
            for c in entry.get("cue_points", [])
        ],
        stems=StemPaths(vocals="", drums="", bass="", other=""),
    )


_load_library()  # hydrate on startup


class LibraryScanRequest(BaseModel):
    folder: str


async def _run_scan(scan_id: str, folder: str) -> None:
    try:
        td = Path(folder).resolve()
        if not td.is_dir():
            _scan_jobs[scan_id].update(status="error", error=f"Not a directory: {folder}")
            return

        files = sorted(str(p) for p in td.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if not files:
            _scan_jobs[scan_id].update(status="error", error="No audio files found")
            return

        _scan_jobs[scan_id]["total"] = len(files)
        loop = asyncio.get_running_loop()
        known, new_count = 0, 0

        for i, path in enumerate(files):
            _scan_jobs[scan_id]["progress"] = i
            h = await loop.run_in_executor(_bg_executor, file_hash, path)

            if h in _library:
                _library[h]["path"] = path  # update path in case file moved
                known += 1
                continue

            # New track — fast analysis (no stems)
            analysis = await loop.run_in_executor(
                _bg_executor, _analyze_track, path, f"lib_{h[:8]}", True
            )
            _library[h] = _entry_from_analysis(analysis, h)
            _save_library()
            new_count += 1
            _scan_jobs[scan_id]["new"] = new_count

        _scan_jobs[scan_id].update(
            status="done", progress=len(files), known=known, new=new_count
        )
    except Exception as exc:
        _scan_jobs[scan_id].update(status="error", error=str(exc))


@app.post("/api/library/scan")
async def library_scan(req: LibraryScanRequest, background_tasks: BackgroundTasks):
    scan_id = str(uuid.uuid4())
    _scan_jobs[scan_id] = {
        "status": "running", "progress": 0, "total": 0, "known": 0, "new": 0, "error": None
    }
    background_tasks.add_task(_run_scan, scan_id, req.folder)
    return {"scan_id": scan_id}


@app.get("/api/library/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    job = _scan_jobs.get(scan_id)
    if not job:
        return JSONResponse({"error": "scan not found"}, status_code=404)
    return job


@app.get("/api/library")
async def get_library():
    tracks = sorted(
        _library.values(),
        key=lambda t: (t.get("artist", "").lower(), t.get("title", "").lower()),
    )
    return {"tracks": tracks, "total": len(tracks)}


# ─── Auto-DJ Session ──────────────────────────────────────────────────────────

def _make_play_script(analysis: TrackAnalysis, track_id: str) -> MixScript:
    return MixScript(
        mix_title="Claude DJ — Live",
        reasoning=f"Now playing: {analysis.title}",
        tracks=[MixTrackRef(
            id=track_id, path=analysis.file,
            bpm=analysis.bpm, first_downbeat_s=analysis.first_downbeat_s,
        )],
        actions=[MixAction(type="play", track=track_id, at_bar=0, from_bar=0)],
    )


def _load_one_track_sync(
    analysis: TrackAnalysis,
    track_id: str,
    ref_bpm: float,
) -> tuple[dict, dict]:
    """Load and time-stretch one track. Returns (loaded_dict, stem_layers_dict)."""
    seg = load_track(analysis.file)
    first_db_ms = int(analysis.first_downbeat_s * 1000)
    if first_db_ms > 0:
        seg = seg[first_db_ms:]
    seg = time_stretch(seg, analysis.bpm, ref_bpm)
    loaded = {track_id: seg}

    stems: dict[tuple[str, str], AudioSegment] = {}
    for stem_name in ("drums", "bass", "vocals", "other"):
        p = Path(getattr(analysis.stems, stem_name, ""))
        if p.exists():
            s = AudioSegment.from_wav(str(p))
            s = time_stretch(s, analysis.bpm, ref_bpm)
            if s.frame_rate != seg.frame_rate:
                s = s.set_frame_rate(seg.frame_rate)
            stems[(track_id, stem_name)] = s

    if loaded[track_id].frame_rate != seg.frame_rate:
        loaded[track_id] = loaded[track_id].set_frame_rate(seg.frame_rate)

    return loaded, stems


def _merge_transition(
    global_script: MixScript,
    sub_script: MixScript,
    current_id: str,
    next_id: str,
    offset: int,
) -> tuple[MixScript, int]:
    """
    Merge a 2-track sub-script (T1=current_id, T2=next_id) into global_script,
    offsetting all bar numbers by `offset` (global bar where current_id started).
    Returns (new_global_script, next_track_start_bar_in_global).
    """
    sub_id_map = {"T1": current_id, "T2": next_id}

    # Add next track ref if not already present
    new_tracks = list(global_script.tracks)
    next_ref = next((t for t in sub_script.tracks if t.id == "T2"), None)
    if next_ref and not any(t.id == next_id for t in new_tracks):
        new_tracks.append(dataclasses.replace(next_ref, id=next_id))

    new_actions = list(global_script.actions)
    next_start_bar = offset  # fallback if no play T2 action found

    for a in sub_script.actions:
        # Skip the leading "play T1 at_bar=0" — already in global script
        if a.type == "play" and a.track == "T1" and (a.at_bar or 0) == 0:
            continue
        global_track = sub_id_map.get(a.track, a.track)
        new_a = dataclasses.replace(
            a,
            track     = global_track,
            at_bar    = ((a.at_bar    or 0) + offset) if a.at_bar    is not None else None,
            start_bar = ((a.start_bar or 0) + offset) if a.start_bar is not None else None,
            bar       = ((a.bar       or 0) + offset) if a.bar       is not None else None,
        )
        new_actions.append(new_a)
        if a.type == "play" and a.track == "T2":
            next_start_bar = (a.at_bar or 0) + offset

    # Keep actions in bar-ascending order so render_chunk can process them correctly
    def _action_bar(act: MixAction) -> int:
        return act.at_bar or act.start_bar or act.bar or 0

    return (
        MixScript(
            mix_title=global_script.mix_title,
            reasoning=global_script.reasoning,
            tracks=new_tracks,
            actions=sorted(new_actions, key=_action_bar),
        ),
        next_start_bar,
    )


def _pick_claude_sync(
    current_analysis: TrackAnalysis,
    pool_hashes: list[str],
    model: str,
) -> str:
    candidates = [
        _analysis_from_entry(_library[h], h)
        for h in pool_hashes[:10]
        if h in _library
    ]
    if not candidates:
        return pool_hashes[0]
    chosen_id = select_next_track(current_analysis, candidates, model)
    # candidates[i].id == hash (we use full hash as ID)
    if chosen_id in pool_hashes:
        return chosen_id
    return pool_hashes[0]


async def _dj_worker(dj_id: str) -> None:
    """Rolling auto-DJ pipeline: T1 → T2 → T3 … with lazy planning."""
    sess  = _dj_sessions[dj_id]
    model = sess["model"]
    loop  = asyncio.get_running_loop()

    def _pop_next() -> Optional[str]:
        """Return next hash from user queue, or None (let caller pick from pool)."""
        q = sess.get("queue", [])
        return q.pop(0) if q else None

    def _available_pool() -> list[str]:
        return [h for h in sess.get("pool", []) if h not in sess.get("history", [])]

    # ── Phase 1: start T1 ───────────────────────────────────────────────────
    first_hash = _pop_next() or (_available_pool() or [None])[0]
    if not first_hash or first_hash not in _library:
        sess.update(status="error", error="No tracks available to start")
        return

    sess.setdefault("history", []).append(first_hash)
    sess["deck_b"] = {"status": "starting", "title": "…"}

    try:
        first_analysis = await loop.run_in_executor(
            _bg_executor, _analyze_track,
            _library[first_hash]["path"], "T1", True,
        )
    except Exception as exc:
        sess.update(status="error", error=f"T1 analysis failed: {exc}")
        return

    ref_bpm = first_analysis.bpm
    try:
        loaded, stems = await loop.run_in_executor(
            _bg_executor, _load_one_track_sync, first_analysis, "T1", ref_bpm,
        )
    except Exception as exc:
        sess.update(status="error", error=f"T1 load failed: {exc}")
        return

    script    = _make_play_script(first_analysis, "T1")
    scheduler = ChunkScheduler(script, loaded, stems, ref_bpm)
    await scheduler.start()

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "status":        "ready",
        "script":        script,
        "scheduler":     scheduler,
        "ref_bpm":       ref_bpm,
        "tracks":        [dataclasses.asdict(t) for t in script.tracks],
        "load_progress": 1,
        "load_total":    1,
        "error":         None,
    }
    sess.update(
        session_id     = session_id,
        status         = "playing",
        ref_bpm        = ref_bpm,
        track_counter  = 1,
        current_start_bar = 0,
        deck_a = {
            "track_id": "T1", "hash": first_hash,
            "title": first_analysis.title, "start_bar": 0, "status": "playing",
        },
        deck_b = None,
    )
    current_analysis = first_analysis

    # ── Phase 2: rolling transitions ────────────────────────────────────────
    for _step in range(1, 200):
        if sess.get("status") != "playing":
            break

        current_id    = f"T{sess['track_counter']}"
        current_hash  = sess["deck_a"]["hash"]
        current_start = sess["current_start_bar"]

        # Pick next track
        next_hash = _pop_next()
        if not next_hash:
            pool = _available_pool()
            if not pool:
                break  # library exhausted
            if sess.get("let_claude_pick", True) and os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    next_hash = await loop.run_in_executor(
                        _bg_executor, _pick_claude_sync,
                        current_analysis, pool, model,
                    )
                except Exception:
                    next_hash = pool[0]
            else:
                next_hash = pool[0]

        if not next_hash or next_hash not in _library:
            break

        sess["history"].append(next_hash)
        next_tc = sess["track_counter"] + 1
        next_id = f"T{next_tc}"
        sess["deck_b"] = {
            "status": "analyzing",
            "title": _library[next_hash].get("title", "…"),
        }

        # Analyze next track (fast — uses cache if available)
        try:
            next_analysis = await loop.run_in_executor(
                _bg_executor, _analyze_track,
                _library[next_hash]["path"], next_id, True,
            )
        except Exception as exc:
            print(f"[dj_worker] analyze {next_id} failed: {exc}")
            sess["deck_b"] = None
            continue

        sess["deck_b"]["status"] = "planning"

        # Plan T_current → T_next with Claude
        try:
            sub_script: MixScript = await loop.run_in_executor(
                _bg_executor, direct_mix,
                [current_analysis, next_analysis], model, None,
            )
            sub_script = normalize(sub_script)
        except Exception as exc:
            print(f"[dj_worker] plan {current_id}→{next_id} failed: {exc}")
            sess["deck_b"] = None
            continue

        sess["deck_b"]["status"] = "loading"

        # Load T_next audio
        try:
            extra_loaded, extra_stems = await loop.run_in_executor(
                _bg_executor, _load_one_track_sync, next_analysis, next_id, ref_bpm,
            )
        except Exception as exc:
            print(f"[dj_worker] load {next_id} failed: {exc}")
            sess["deck_b"] = None
            continue

        # Merge transition into live global script
        global_script = _sessions[session_id]["script"]
        new_script, next_start_bar = _merge_transition(
            global_script, sub_script, current_id, next_id, current_start,
        )
        scheduler.extend(new_script, extra_loaded, extra_stems)
        _sessions[session_id]["script"] = new_script

        sess["deck_b"]["status"] = "ready"
        sess["track_counter"] = next_tc

        # Wait until playback has passed T_next's start bar (transition complete)
        while scheduler.current_bar < next_start_bar + 8:
            await asyncio.sleep(2.0)
            if sess.get("status") != "playing":
                return

        # Advance deck A
        sess.update(
            deck_a = {
                "track_id": next_id, "hash": next_hash,
                "title": next_analysis.title,
                "start_bar": next_start_bar, "status": "playing",
            },
            deck_b = None,
            current_start_bar = next_start_bar,
        )
        current_analysis = next_analysis


class DjStartRequest(BaseModel):
    pool:           list[str] = []        # file hashes from library
    queue:          list[str] = []        # ordered hashes to play first
    let_claude_pick: bool     = True
    model:          str       = "claude-sonnet-4-6"


@app.post("/api/dj/start")
async def dj_start(req: DjStartRequest, background_tasks: BackgroundTasks):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY not set."}, status_code=503,
        )

    # Resolve any paths to hashes (client may send either)
    def _to_hash(val: str) -> Optional[str]:
        if val in _library:
            return val
        # Try matching by path
        for h, e in _library.items():
            if e.get("path") == val:
                return h
        return None

    pool  = [h for v in req.pool  if (h := _to_hash(v))]
    queue = [h for v in req.queue if (h := _to_hash(v))]

    if not pool and not queue:
        # Use entire library as pool
        pool = list(_library.keys())

    dj_id = str(uuid.uuid4())
    _dj_sessions[dj_id] = {
        "status":         "starting",
        "model":          req.model,
        "let_claude_pick": req.let_claude_pick,
        "pool":           pool,
        "queue":          queue,
        "history":        [],
        "session_id":     None,
        "deck_a":         None,
        "deck_b":         {"status": "starting", "title": "…"},
        "track_counter":  0,
        "current_start_bar": 0,
        "ref_bpm":        None,
        "error":          None,
    }

    background_tasks.add_task(_dj_worker, dj_id)
    return {"dj_id": dj_id}


@app.get("/api/dj/{dj_id}")
async def get_dj_state(dj_id: str):
    sess = _dj_sessions.get(dj_id)
    if not sess:
        return JSONResponse({"error": "dj session not found"}, status_code=404)

    session_id = sess.get("session_id")
    script_summary = None
    if session_id and session_id in _sessions:
        s = _sessions[session_id].get("script")
        if s:
            script_summary = _sanitize(dataclasses.asdict(s))

    return _sanitize({
        "status":     sess["status"],
        "session_id": session_id,
        "deck_a":     sess.get("deck_a"),
        "deck_b":     sess.get("deck_b"),
        "history":    sess.get("history", []),
        "queue":      sess.get("queue", []),
        "ref_bpm":    sess.get("ref_bpm"),
        "script":     script_summary,
        "error":      sess.get("error"),
    })


@app.post("/api/dj/{dj_id}/queue")
async def dj_enqueue(dj_id: str, body: dict):
    """Add a track hash (or path) to the front of the DJ session queue."""
    sess = _dj_sessions.get(dj_id)
    if not sess:
        return JSONResponse({"error": "dj session not found"}, status_code=404)
    h = body.get("hash") or body.get("path")
    if not h or h not in _library:
        # Try path lookup
        for lh, e in _library.items():
            if e.get("path") == h:
                h = lh
                break
    if h not in _library:
        return JSONResponse({"error": "track not in library"}, status_code=400)
    sess.setdefault("queue", []).append(h)
    return {"queued": h, "queue_length": len(sess["queue"])}


# ─── Cleanup ──────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def _shutdown() -> None:
    for sess in _sessions.values():
        sched = sess.get("scheduler")
        if sched is not None:
            await sched.stop()


# ─── Static frontend ──────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")
