# claude-dj/dj_session.py
"""
Auto-DJ session worker and helpers.
Extracted from server.py so that routes stay thin and this module is testable.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import time as _time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydub import AudioSegment

from audio_queue import ChunkScheduler
from executor import (
    apply_loudness_match, bars_to_ms,
    load_track, time_stretch,
)
from library import Library
from mix_director import (
    direct_mix, select_next_track,
    select_transition_window, plan_transition,
)
from analyze import analyze_transition_zone as _analyze_zone
from normalizer import normalize
from schema import MixAction, MixScript, MixTrackRef, TrackAnalysis
from state import (
    AudioSession, AudioSessionStore, DjDeckA, DjDeckB,
    DjSessionState, DjSessionStore, TransitionLogEntry,
)

_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dj-worker")


def make_play_script(analysis: TrackAnalysis, track_id: str) -> MixScript:
    return MixScript(
        mix_title="Claude DJ — Live",
        reasoning=f"Now playing: {analysis.title}",
        tracks=[MixTrackRef(
            id=track_id, path=analysis.file,
            bpm=analysis.bpm, first_downbeat_s=analysis.first_downbeat_s,
        )],
        actions=[MixAction(type="play", track=track_id, at_bar=0, from_bar=0)],
    )


def load_one_track(
    analysis: TrackAnalysis,
    track_id: str,
    ref_bpm: float,
) -> tuple[dict, dict]:
    """Load, loudness-match, and time-stretch one track. Returns (loaded_dict, stem_layers_dict)."""
    from pathlib import Path as _Path
    if not analysis.file or not _Path(analysis.file).is_file():
        raise ValueError(f"audio file not found or invalid: {analysis.file!r}")
    seg = load_track(analysis.file)
    first_db_ms = int(analysis.first_downbeat_s * 1000)
    if first_db_ms > 0:
        seg = seg[first_db_ms:]
    seg = apply_loudness_match(seg, analysis.loudness_dbfs)
    seg = time_stretch(seg, analysis.bpm, ref_bpm)
    loaded = {track_id: seg}

    stems: dict[tuple[str, str], AudioSegment] = {}
    if analysis.stems is not None:
        for stem_name in ("drums", "bass", "vocals", "other"):
            p = Path(getattr(analysis.stems, stem_name, ""))
            if p.is_file():
                s = AudioSegment.from_wav(str(p))
                s = apply_loudness_match(s, analysis.loudness_dbfs)
                s = time_stretch(s, analysis.bpm, ref_bpm)
                if s.frame_rate != seg.frame_rate:
                    s = s.set_frame_rate(seg.frame_rate)
                stems[(track_id, stem_name)] = s

    if loaded[track_id].frame_rate != seg.frame_rate:
        loaded[track_id] = loaded[track_id].set_frame_rate(seg.frame_rate)

    return loaded, stems


def merge_transition(
    global_script: MixScript,
    sub_script: MixScript,
    current_id: str,
    next_id: str,
    t2_offset: int,
    t1_offset: int = 0,
) -> tuple[MixScript, int]:
    """
    Merge a 2-track sub-script (T1=current_id, T2=next_id) into global_script.

    Sub-script bars are in track-local space (bar 0 = each track's first downbeat).
    They need two DIFFERENT global offsets:

      t1_offset  = global bar where current track started playing (= current_start_bar).
                   T1 local bar 80 → global bar 80 + t1_offset.
      t2_offset  = global bar where T2's content should begin (= adjusted_offset,
                   set to TRANSITION_LOOKAHEAD bars ahead of actual playback).
                   T2 local bar 0 → global bar 0 + t2_offset.

    Using the same offset for both (the old behaviour) caused the outgoing track's
    fade_out to land past its audio end on all transitions after the first, because
    adjusted_offset >> current_start once the mix has been running for a while.
    """
    sub_id_map = {"T1": current_id, "T2": next_id}

    new_tracks = list(global_script.tracks)
    next_ref = next((t for t in sub_script.tracks if t.id == "T2"), None)
    if next_ref and not any(t.id == next_id for t in new_tracks):
        new_tracks.append(dataclasses.replace(next_ref, id=next_id))

    new_actions = list(global_script.actions)
    next_start_bar = t2_offset

    for a in sub_script.actions:
        if a.type == "play" and a.track == "T1" and (a.at_bar or 0) == 0:
            continue
        global_track = sub_id_map.get(a.track, a.track)
        bar_off = t1_offset if a.track == "T1" else t2_offset
        new_a = dataclasses.replace(
            a,
            track     = global_track,
            at_bar    = ((a.at_bar    or 0) + bar_off) if a.at_bar    is not None else None,
            start_bar = ((a.start_bar or 0) + bar_off) if a.start_bar is not None else None,
            bar       = ((a.bar       or 0) + bar_off) if a.bar       is not None else None,
        )
        new_actions.append(new_a)
        if a.type == "play" and a.track == "T2":
            next_start_bar = (a.at_bar or 0) + t2_offset

    def _action_bar(act: MixAction) -> int:
        return act.at_bar or act.start_bar or act.bar or 0

    combined_reasoning = (
        (global_script.reasoning or "").rstrip()
        + "\n\n---\n\n"
        + (sub_script.reasoning or "")
    ).strip()

    return (
        MixScript(
            mix_title=global_script.mix_title,
            reasoning=combined_reasoning,
            tracks=new_tracks,
            actions=sorted(new_actions, key=_action_bar),
        ),
        next_start_bar,
    )


def pick_next_track(
    current: TrackAnalysis,
    pool: list[str],
    library: Library,
    model: str,
) -> str:
    """Ask Claude to pick the best-fitting next track from the pool."""
    eligible = [h for h in pool[:10] if library.get(h) is not None]
    if not eligible:
        return pool[0]
    # Use short numeric IDs so Claude can return "1", "2" etc. reliably
    candidates = [library.to_analysis(h, str(i + 1)) for i, h in enumerate(eligible)]
    chosen_id = select_next_track(current, candidates, model)
    if chosen_id.isdigit():
        idx = int(chosen_id) - 1
        if 0 <= idx < len(eligible):
            return eligible[idx]
    return eligible[0]


async def dj_worker(
    dj_id: str,
    dj_store: DjSessionStore,
    audio_store: AudioSessionStore,
    library: Library,
) -> None:
    """Rolling auto-DJ pipeline: T1 → T2 → T3 … with lazy planning."""
    state = dj_store.get(dj_id)
    model = state.model
    loop = asyncio.get_running_loop()

    def _pop_next() -> Optional[str]:
        return state.queue.pop(0) if state.queue else None

    def _available_pool() -> list[str]:
        available = [h for h in state.pool if h not in state.history]
        if not available:
            # All tracks played — wrap around, excluding only the current track
            playing_now = state.deck_a.hash if state.deck_a else None
            state.history = [playing_now] if playing_now else []
            available = [h for h in state.pool if h not in state.history]
        return available

    # ── Phase 1: start T1 ───────────────────────────────────────────────────
    first_hash = _pop_next() or (_available_pool() or [None])[0]
    if not first_hash or library.get(first_hash) is None:
        state.status = "error"
        state.error = "No tracks available to start"
        return

    state.history.append(first_hash)
    state.deck_b = DjDeckB(status="analyzing", title="first track")

    try:
        from analyze import analyze_track as _analyze_track
        first_entry = library.get(first_hash)
        state.deck_b = DjDeckB(status="analyzing", title=first_entry.title)
        first_analysis = await loop.run_in_executor(
            _bg_executor, _analyze_track,
            first_entry.path, "T1", True,
        )
    except Exception as exc:
        state.status = "error"
        state.error = f"T1 analysis failed: {exc}"
        return

    ref_bpm = first_analysis.bpm
    try:
        state.deck_b = DjDeckB(status="loading", title=first_analysis.title)
        loaded, stems = await loop.run_in_executor(
            _bg_executor, load_one_track, first_analysis, "T1", ref_bpm,
        )
    except Exception as exc:
        state.status = "error"
        state.error = f"T1 load failed: {exc}"
        return

    script = make_play_script(first_analysis, "T1")
    scheduler = ChunkScheduler(script, loaded, stems, ref_bpm)
    # total_mix_ms is computed correctly in ChunkScheduler.__init__ — no override needed.
    await scheduler.start()

    session_id = str(uuid.uuid4())
    audio_store.create(session_id, AudioSession(
        session_id    = session_id,
        status        = "ready",
        script        = script,
        scheduler     = scheduler,
        ref_bpm       = ref_bpm,
        tracks        = [dataclasses.asdict(t) for t in script.tracks],
        load_progress = 1,
        load_total    = 1,
    ))

    state.session_id        = session_id
    state.status            = "playing"
    state.ref_bpm           = ref_bpm
    state.track_counter     = 1
    state.current_start_bar = 0
    state.deck_a = DjDeckA(
        track_id  = "T1",
        hash      = first_hash,
        title     = first_analysis.title,
        start_bar = 0,
    )
    state.deck_b = None
    current_analysis = first_analysis

    # Wall-clock reference: when did this session start playing?
    # Used to compute actual playback bar (independent of how far ahead the scheduler rendered).
    session_wall_start = _time.monotonic()
    secs_per_bar = 4 * 60 / ref_bpm
    TRANSITION_LOOKAHEAD = 32  # bars ahead of actual playback to place T2 start

    # ── Phase 2: rolling transitions ────────────────────────────────────────
    for _step in range(1, 200):
        if state.status != "playing":
            break

        current_id    = f"T{state.track_counter}"
        current_hash  = state.deck_a.hash
        current_start = state.current_start_bar

        next_hash = _pop_next()
        if not next_hash:
            pool = _available_pool()
            if not pool:
                break
            if state.let_claude_pick and os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    next_hash = await loop.run_in_executor(
                        _bg_executor, pick_next_track,
                        current_analysis, pool, library, model,
                    )
                except Exception:
                    next_hash = pool[0]
            else:
                next_hash = pool[0]

        if not next_hash or library.get(next_hash) is None:
            break

        state.history.append(next_hash)
        next_tc = state.track_counter + 1
        next_id = f"T{next_tc}"
        next_entry = library.get(next_hash)
        state.deck_b = DjDeckB(status="analyzing", title=next_entry.title, hash=next_hash)

        try:
            from analyze import analyze_track as _analyze_track
            next_analysis = await loop.run_in_executor(
                _bg_executor, _analyze_track,
                next_entry.path, next_id, True,
            )
        except Exception as exc:
            print(f"[dj_worker] analyze {next_id} failed: {exc}")
            state.deck_b = None
            continue

        # ── Phase 1: select transition window (lightweight API call) ────────────
        state.deck_b = DjDeckB(status="selecting", title=next_analysis.title, hash=next_hash)

        t1_labeled = dataclasses.replace(current_analysis, id="T1")
        t2_labeled = dataclasses.replace(next_analysis,    id="T2")

        try:
            window: dict = await loop.run_in_executor(
                _bg_executor, select_transition_window,
                t1_labeled, t2_labeled, model,
            )
            print(
                f"[dj_worker] window selected: T1 exit bar={window['t1_exit_bar']} "
                f"T2 enter bar={window['t2_enter_bar']} overlap={window['window_bars']} "
                f"style={window['style']}"
            )
        except Exception as exc:
            err_str = str(exc)
            print(f"[dj_worker] select_window {current_id}→{next_id} failed: {exc}")
            state.deck_b = None
            if "credit balance" in err_str or "invalid_api_key" in err_str or "authentication" in err_str.lower():
                state.status = "error"
                state.error = f"Anthropic API error: {exc}"
                return
            await asyncio.sleep(5)
            continue

        # ── Phase 2a: deep zone analysis (CPU only, ~1-2s per track) ─────────
        state.deck_b = DjDeckB(status="planning", title=next_analysis.title, hash=next_hash)

        # Run both zone analyses in parallel in the background executor
        t1_zone_future = loop.run_in_executor(
            _bg_executor, _analyze_zone,
            current_analysis.file, current_analysis.bpm, current_analysis.first_downbeat_s,
            max(0, window["t1_exit_bar"] - 8), 56,  # 8-bar lead-in, 56-bar window
        )
        t2_zone_future = loop.run_in_executor(
            _bg_executor, _analyze_zone,
            next_analysis.file, next_analysis.bpm, next_analysis.first_downbeat_s,
            window["t2_enter_bar"], 48,
        )
        try:
            t1_zone, t2_zone = await asyncio.gather(t1_zone_future, t2_zone_future)
            print(f"[dj_worker] zone analysis done: T1={len(t1_zone)} bars, T2={len(t2_zone)} bars")
        except Exception as exc:
            print(f"[dj_worker] zone analysis failed ({exc}) — continuing with empty zones")
            t1_zone, t2_zone = [], []

        # ── Phase 2b: move planning (richer zone context) ─────────────────────
        try:
            sub_script: MixScript = await loop.run_in_executor(
                _bg_executor, plan_transition,
                t1_labeled, t2_labeled, t1_zone, t2_zone, window, model,
            )
            sub_script = normalize(sub_script)
        except Exception as exc:
            err_str = str(exc)
            print(f"[dj_worker] plan_transition {current_id}→{next_id} failed: {exc}")
            state.deck_b = None
            if "credit balance" in err_str or "invalid_api_key" in err_str or "authentication" in err_str.lower():
                state.status = "error"
                state.error = f"Anthropic API error: {exc}"
                return
            await asyncio.sleep(5)
            continue

        state.deck_b = DjDeckB(status="loading", title=next_analysis.title, hash=next_hash)

        try:
            extra_loaded, extra_stems = await loop.run_in_executor(
                _bg_executor, load_one_track, next_analysis, next_id, ref_bpm,
            )
        except Exception as exc:
            print(f"[dj_worker] load {next_id} failed: {exc}")
            state.deck_b = None
            continue

        audio_sess = audio_store.get(session_id)
        global_script = audio_sess.script

        # Compute where we actually are in playback using wall clock — much more accurate than
        # scheduler.current_bar which advances at render speed (can be 10x ahead of playback).
        now = _time.monotonic()
        actual_playback_bar = (now - session_wall_start) / secs_per_bar

        # Find where the sub_script's T2 play action starts (relative to sub_script bar 0)
        sub_t2_first = 0
        for a in sub_script.actions:
            if a.type == "play" and a.track == "T2":
                sub_t2_first = a.at_bar or 0
                break

        # Find T2's EARLIEST action bar in sub_script (fade_in starts before play)
        sub_t2_earliest = sub_t2_first
        for a in sub_script.actions:
            if a.track == "T2":
                bar = a.start_bar or a.at_bar or a.bar or 0
                if bar < sub_t2_earliest:
                    sub_t2_earliest = bar

        # Soft lower bound: keep transition TRANSITION_LOOKAHEAD bars past actual playback.
        min_offset = int(actual_playback_bar) - sub_t2_first + TRANSITION_LOOKAHEAD

        # Hard lower bound: T2's earliest action must land AFTER the render head.
        # Use a tight margin (8 bars ≈ 15s) — the pacing bound (MAX_LOOKAHEAD_SECS=30)
        # keeps the render head only ~16 bars ahead, so 8 bars extra is plenty of headroom.
        render_head = audio_sess.scheduler._render_bar
        min_offset_render = render_head - sub_t2_earliest + 8  # 8-bar margin past render head

        adjusted_offset = max(current_start, min_offset, min_offset_render)
        if adjusted_offset != current_start:
            print(f"[dj_worker] transition shifted +{adjusted_offset - current_start} bars "
                  f"(actual_playback_bar={actual_playback_bar:.1f}, render_head={render_head}, "
                  f"planned={current_start})")

        new_script, next_start_bar = merge_transition(
            global_script, sub_script, current_id, next_id,
            t2_offset=adjusted_offset,
            t1_offset=current_start,
        )
        scheduler.extend(new_script, extra_loaded, extra_stems)
        audio_sess.script = new_script

        # ── Transition log ───────────────────────────────────────────────────
        state.transition_log.append(TransitionLogEntry(
            ts          = datetime.now(timezone.utc).isoformat(),
            from_id     = current_id,
            to_id       = next_id,
            from_title  = current_analysis.title,
            to_title    = next_analysis.title,
            offset_bar  = next_start_bar,
            reasoning   = sub_script.reasoning or "",
            actions     = [dataclasses.asdict(a) for a in sub_script.actions],
        ))

        state.deck_b = DjDeckB(status="ready", title=next_analysis.title, hash=next_hash)
        state.track_counter = next_tc

        # Wait until actual audio playback reaches next_start_bar, then flip deck labels.
        # Use wall-clock calculation — scheduler.current_bar is unreliable (ahead of audio).
        # We wait until t2_play_wall (no extra grace) so the deck label matches what's
        # audibly playing. A small early flip is fine; a 2s late flip desynchronises the UI.
        t2_play_wall = session_wall_start + next_start_bar * secs_per_bar
        while _time.monotonic() < t2_play_wall:
            await asyncio.sleep(0.25)
            if state.status != "playing":
                return

        state.deck_a = DjDeckA(
            track_id  = next_id,
            hash      = next_hash,
            title     = next_analysis.title,
            start_bar = next_start_bar,
        )
        state.deck_b = None
        state.current_start_bar = next_start_bar
        current_analysis = next_analysis
        # Update wall-clock reference for the new current track
        session_wall_start = _time.monotonic() - next_start_bar * secs_per_bar

    # Worker exited the transition loop — pool exhausted or step limit reached.
    if state.status == "playing":
        state.status = "stopped"
        print(f"[dj_worker] session {dj_id} finished — pool exhausted or step limit reached")
