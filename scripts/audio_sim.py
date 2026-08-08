#!/usr/bin/env python3
"""
Full audio simulation — plans, renders, and mechanically analyses DJ transitions.

For each pair this pipeline:
  1. Plans the transition (Phase 1 + Phase 2 + normalize) via the LLM
  2. Loads + time-stretches both tracks
  3. Renders three versions of the transition window (~60s each):
       mix.wav     — full stereo blend (what you'd hear)
       t1_solo.wav — T1 track in isolation, with all T1 actions applied
       t2_solo.wav — T2 track in isolation, with all T2 actions applied
  4. Mechanically analyses the rendered audio:
       • Per-bar RMS for T1-solo, T2-solo, full mix
       • T1 fade-out monotonicity + snap-back detection
       • T2 fade-in monotonicity
       • Mix energy holes (silence > 2 bars)
       • Mix clipping
       • Bass transfer: LPF<200 Hz RMS on T1 vs T2 around bass_swap point
  5. Writes per-pair report.txt (ASCII gain graphs + findings) + analysis.json
  6. Prints a batch summary table

Usage:
  cd "/Users/DantesFolder/Claude DJ"
  python3 scripts/audio_sim.py [--pairs N] [--out DIR]

Output:
  audio_sims/<timestamp>/<pair_idx>/
    mix.wav / t1_solo.wav / t2_solo.wav
    report.txt   (human + AI readable)
    analysis.json
  audio_sims/<timestamp>/summary.txt
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import argparse
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "claude-dj"))

from schema import MixScript, MixAction, MixTrackRef, TrackAnalysis
from mix_director import select_transition_window, plan_transition, _camelot_distance
from normalizer import normalize
from executor import bars_to_ms, load_track, time_stretch, render_chunk

# ── CLI ───────────────────────────────────────────────────────────────────────

_ap = argparse.ArgumentParser()
_ap.add_argument("--pairs", type=int, default=4, help="Number of pairs to simulate (default 4)")
_ap.add_argument("--out", type=str, default=None, help="Output directory (default audio_sims/<ts>)")
_CLI = _ap.parse_args()

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL        = "claude-haiku-4-5-20251001"
LIBRARY_PATH = PROJECT_ROOT / "claude-dj" / "cache" / "library.json"
CACHE_DIR    = PROJECT_ROOT / "claude-dj" / "cache"
OUT_DIR      = Path(_CLI.out) if _CLI.out else (
    PROJECT_ROOT / "audio_sims" / datetime.now().strftime("%Y%m%d_%H%M%S")
)
BPM_LOW, BPM_HIGH = 118, 135
MAX_PAIRS = _CLI.pairs
FRAME_MS  = 250          # RMS sampling resolution
SNAP_BACK_THRESH_DB = -25.0   # T1 RMS above this after fade_out = snap-back
HOLE_THRESH_DB      = -45.0   # mix RMS below this = energy hole
MONO_TOL_DB         = 1.5     # allowed RMS increase per frame during a fade-down

# ── Env ───────────────────────────────────────────────────────────────────────

def _load_env() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_path = PROJECT_ROOT / "claude-dj" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found")
        sys.exit(1)

_load_env()

# ── Library + pairs ───────────────────────────────────────────────────────────

@dataclass
class Pair:
    t1: TrackAnalysis
    t2: TrackAnalysis
    camelot_dist: int
    bpm_delta: float


def _load_analyses() -> list[TrackAnalysis]:
    from analyze import analyze_track
    lib = json.loads(LIBRARY_PATH.read_text())
    out = []
    for track_hash, meta in lib.items():
        path = meta.get("path", "")
        if not path.endswith(".mp3"):
            continue
        if not (BPM_LOW <= meta.get("bpm", 0) <= BPM_HIGH):
            continue
        if not meta.get("key_camelot"):
            continue
        if not Path(path).exists():
            continue
        cache_file = CACHE_DIR / track_hash / "analysis.json"
        if not cache_file.exists():
            continue
        try:
            out.append(analyze_track(path, track_hash, no_stems=True))
        except Exception as exc:
            print(f"  SKIP {Path(path).name}: {exc}")
    return out


def _build_pairs(tracks: list[TrackAnalysis]) -> list[Pair]:
    pairs: list[Pair] = []
    seen: set[tuple[str, str]] = set()
    for t1 in tracks:
        for t2 in tracks:
            if t1 is t2:
                continue
            key = tuple(sorted([t1.id, t2.id]))
            if key in seen:
                continue
            seen.add(key)
            dist = _camelot_distance(
                getattr(t1.key, "camelot", ""),
                getattr(t2.key, "camelot", ""),
            )
            if dist > 1:
                continue
            pairs.append(Pair(t1=t1, t2=t2, camelot_dist=dist,
                               bpm_delta=abs(t1.bpm - t2.bpm)))
    pairs.sort(key=lambda p: (p.camelot_dist, p.bpm_delta))
    per = max(1, MAX_PAIRS // 4)
    buckets = [
        [p for p in pairs if p.camelot_dist == 0 and p.bpm_delta == 0][:per],
        [p for p in pairs if p.camelot_dist == 0 and p.bpm_delta > 0][:per],
        [p for p in pairs if p.camelot_dist == 1 and p.bpm_delta == 0][:per],
        [p for p in pairs if p.camelot_dist == 1 and p.bpm_delta > 0][:per],
    ]
    selected: list[Pair] = []
    for b in buckets:
        selected.extend(b)
    return selected[:MAX_PAIRS]

# ── Solo-script builders ───────────────────────────────────────────────────────

def _solo_script(script: MixScript, keep_tid: str) -> MixScript:
    """Return a MixScript that only activates one track (strips the other's play)."""
    other = "T2" if keep_tid == "T1" else "T1"
    kept = []
    for a in script.actions:
        if a.track == other:
            continue
        # strip bass_swap (references both tracks; irrelevant for solo)
        if a.type == "bass_swap":
            continue
        kept.append(a)
    track_refs = [t for t in script.tracks if t.id == keep_tid]
    return MixScript(
        mix_title=script.mix_title,
        reasoning=script.reasoning,
        tracks=track_refs,
        actions=kept,
    )

# ── Audio loading ─────────────────────────────────────────────────────────────

def _load_stretched(ta: TrackAnalysis, ref_bpm: float):
    from pydub import AudioSegment
    seg = load_track(ta.file)
    fdb = int(ta.first_downbeat_s * 1000)
    if fdb > 0:
        seg = seg[fdb:]
    return time_stretch(seg, ta.bpm, ref_bpm)

# ── Rendering ─────────────────────────────────────────────────────────────────

def _render_window(
    script: MixScript,
    loaded: dict,
    ref_bpm: float,
    start_bar: int,
    end_bar: int,
) :
    from pydub import AudioSegment
    target_rate = next(iter(loaded.values())).frame_rate
    bar_ms  = bars_to_ms(1, ref_bpm)
    start_ms = bars_to_ms(start_bar, ref_bpm)
    end_ms   = bars_to_ms(end_bar,   ref_bpm)
    canvas   = AudioSegment.silent(duration=0, frame_rate=target_rate)
    pos = start_ms
    while pos < end_ms:
        chunk_dur = min(bar_ms, end_ms - pos)
        chunk = render_chunk(script, loaded, {}, ref_bpm, pos, chunk_dur)
        canvas = canvas + chunk
        pos += chunk_dur
    return canvas

# ── Analysis ──────────────────────────────────────────────────────────────────

def _rms_profile(seg, frame_ms: int = FRAME_MS) -> list[float]:
    """Sample RMS (dBFS) every frame_ms ms. Returns list of dBFS values (-inf → 0)."""
    values = []
    total = len(seg)
    pos = 0
    while pos < total:
        chunk = seg[pos : pos + frame_ms]
        rms = chunk.rms
        db = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0
        values.append(float(db))
        pos += frame_ms
    return values


def _bar_rms(profile: list[float], render_start_bar: int, ref_bpm: float) -> list[tuple[int, float]]:
    """Average the RMS profile into per-bar values. Returns [(bar_number, avg_db), ...]"""
    bar_ms    = bars_to_ms(1, ref_bpm)
    frames_per_bar = max(1, round(bar_ms / FRAME_MS))
    out = []
    for i in range(0, len(profile), frames_per_bar):
        chunk = profile[i : i + frames_per_bar]
        avg = float(np.mean(chunk))
        bar_num = render_start_bar + (i // frames_per_bar)
        out.append((bar_num, avg))
    return out


def _ms_to_frame(ms: int) -> int:
    return max(0, ms // FRAME_MS)


@dataclass
class FadeCheck:
    ok: bool
    trend_ok: bool          # overall start→end direction is correct
    total_delta_db: float   # signed: negative = fade went down, positive = went up
    extended_reversals: list[dict] = field(default_factory=list)  # runs ≥3 bars wrong way
    start_db: float = 0.0
    end_db: float = 0.0


def _check_fade(
    bar_rms: list[tuple[int, float]],
    fade_start_bar: int,
    fade_end_bar: int,
    direction: str,   # "down" | "up"
) -> FadeCheck:
    """
    Analyse fade quality at bar resolution (avoids transient false positives).

    We check:
      1. trend_ok  — start vs end is in the right direction by ≥ 6 dB
      2. extended_reversals — runs of ≥3 consecutive bars going the wrong way
    """
    window = [(b, v) for b, v in bar_rms if fade_start_bar <= b <= fade_end_bar]
    if len(window) < 2:
        return FadeCheck(ok=True, trend_ok=True, total_delta_db=0.0)

    start_db = window[0][1]
    end_db   = window[-1][1]
    delta    = end_db - start_db   # negative for fade-down, positive for fade-up

    trend_ok = (delta <= -6.0) if direction == "down" else (delta >= 6.0)

    # Detect runs of ≥3 consecutive bars going the wrong way
    reversals = []
    run_start = None
    run_len   = 0
    for i in range(1, len(window)):
        curr_delta = window[i][1] - window[i - 1][1]
        going_wrong = (curr_delta > MONO_TOL_DB) if direction == "down" else (curr_delta < -MONO_TOL_DB)
        if going_wrong:
            if run_start is None:
                run_start = i - 1
            run_len += 1
        else:
            if run_len >= 3:
                reversals.append({
                    "start_bar": window[run_start][0],
                    "length_bars": run_len,
                    "delta_db": round(window[run_start + run_len][1] - window[run_start][1], 2),
                })
            run_start = None
            run_len   = 0
    if run_len >= 3:
        reversals.append({
            "start_bar": window[run_start][0],
            "length_bars": run_len,
            "delta_db": round(window[-1][1] - window[run_start][1], 2),
        })

    ok = trend_ok and len(reversals) == 0
    return FadeCheck(
        ok=ok,
        trend_ok=trend_ok,
        total_delta_db=round(delta, 2),
        extended_reversals=reversals,
        start_db=round(start_db, 2),
        end_db=round(end_db, 2),
    )


def _check_snap_back(profile: list[float], fade_end_ms: int) -> dict:
    """After T1 fade_out ends, RMS should stay below SNAP_BACK_THRESH_DB."""
    i_end = _ms_to_frame(fade_end_ms)
    post = profile[i_end:]
    snaps = [
        {"frame": i_end + i, "db": round(v, 2)}
        for i, v in enumerate(post)
        if v > SNAP_BACK_THRESH_DB
    ]
    return {"ok": len(snaps) == 0, "snap_frames": snaps[:10]}


def _check_energy_holes(profile: list[float]) -> dict:
    """Detect runs of frames where mix RMS < HOLE_THRESH_DB."""
    holes = []
    run_start = None
    for i, v in enumerate(profile):
        if v < HOLE_THRESH_DB:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and (i - run_start) >= 4:
                holes.append({"start_frame": run_start, "length_frames": i - run_start,
                               "length_ms": (i - run_start) * FRAME_MS})
                run_start = None
    return {"ok": len(holes) == 0, "holes": holes}


def _check_clipping(seg) -> dict:
    """Detect digital clipping (peak == max int value)."""
    samples = np.frombuffer(seg.raw_data, dtype=np.int16)
    clip_count = int(np.sum(np.abs(samples) >= 32700))
    return {"ok": clip_count == 0, "clip_samples": clip_count}


def _check_bass_transfer(mix_seg, bass_swap_ms: Optional[int], ref_bpm: float) -> dict:
    """
    Verify the bass_swap causes no audible drop in the mix's low-frequency energy.

    Strategy: LPF the full mix to <200 Hz, then check that the per-bar bass RMS
    stays within ±6 dB of a 4-bar running average around the swap point. A sudden
    bass hole (e.g. both tracks lose bass simultaneously) shows up clearly here.

    We do NOT compare T1 vs T2 in isolation because T1's EQ may already have cut
    its bass by the time the swap fires — that is expected and correct.
    """
    if bass_swap_ms is None:
        return {"ok": None, "note": "no bass_swap action"}

    from pydub.effects import low_pass_filter
    mix_bass   = low_pass_filter(mix_seg, 200)
    bar_ms     = bars_to_ms(1, ref_bpm)
    window_ms  = bars_to_ms(4, ref_bpm)

    # 4-bar window before and after
    pre_start  = max(0, bass_swap_ms - window_ms)
    pre_db     = mix_bass[pre_start:bass_swap_ms].dBFS
    post_end   = bass_swap_ms + window_ms
    post_db    = mix_bass[bass_swap_ms:post_end].dBFS

    # Check per-bar for sudden drops in the ±4 bar window around the swap
    scan_start = max(0, bass_swap_ms - window_ms)
    scan_end   = bass_swap_ms + window_ms
    bar_levels = []
    pos = scan_start
    while pos < scan_end:
        seg = mix_bass[pos : pos + bar_ms]
        if len(seg) > 0:
            bar_levels.append(float(seg.dBFS))
        pos += bar_ms

    sudden_drop = False
    for i in range(1, len(bar_levels)):
        if bar_levels[i] - bar_levels[i - 1] < -8.0:   # >8 dB drop in one bar
            sudden_drop = True
            break

    delta = post_db - pre_db
    # A bass INCREASE is expected (T1 EQ cut → T2 full bass).
    # Only fail on: (a) sudden per-bar drop, or (b) net bass loss > 8 dB (both tracks lose bass).
    ok = not sudden_drop and delta > -8.0

    return {
        "ok": ok,
        "pre_swap_db":  round(pre_db,  2),
        "post_swap_db": round(post_db, 2),
        "delta_db":     round(delta, 2),
        "sudden_drop":  sudden_drop,
        "bar_levels_around_swap": [round(v, 1) for v in bar_levels],
    }

# ── ASCII gain graph ───────────────────────────────────────────────────────────

def _ascii_graph(bar_rms: list[tuple[int, float]], label: str,
                 markers: dict[int, str] | None = None, width: int = 40) -> str:
    """
    Horizontal bar chart of per-bar RMS values.
    Each row: bar_num  ████████  -12.3 dBFS  [MARKER]
    """
    if not bar_rms:
        return f"  {label}: (no data)\n"
    dbs  = [v for _, v in bar_rms]
    lo   = min(-60.0, min(dbs))
    hi   = max(0.0,   max(dbs))
    rng  = hi - lo or 1.0
    lines = [f"\n  {label} (per bar, dBFS)\n  {'─'*(width+28)}"]
    for bar, db in bar_rms:
        filled = int((db - lo) / rng * width)
        bar_str = "█" * max(0, filled) + " " * (width - max(0, filled))
        marker  = f"  ← {markers[bar]}" if markers and bar in markers else ""
        lines.append(f"  bar {bar:4d}  {bar_str}  {db:7.2f} dBFS{marker}")
    return "\n".join(lines) + "\n"

# ── Per-pair runner ────────────────────────────────────────────────────────────

@dataclass
class PairResult:
    pair_id: str
    t1_title: str
    t2_title: str
    ok: bool
    findings: list[str]
    error: Optional[str]
    duration_s: float
    analysis: dict


def _run_pair(pair: Pair, idx: int) -> PairResult:
    from pydub import AudioSegment
    from analyze import analyze_transition_zone as _zone

    pair_id  = f"{idx+1:02d}_{Path(pair.t1.file).stem[:16]}__{Path(pair.t2.file).stem[:16]}"
    pair_dir = OUT_DIR / pair_id
    pair_dir.mkdir(parents=True, exist_ok=True)

    findings: list[str] = []
    analysis: dict = {}
    error: Optional[str] = None
    t_start = time.monotonic()

    print(f"\n{'='*60}")
    print(f"PAIR {idx+1}: {pair.t1.title}  →  {pair.t2.title}")
    print(f"  T1: {pair.t1.bpm:.1f} BPM  {pair.t1.key.camelot}")
    print(f"  T2: {pair.t2.bpm:.1f} BPM  {pair.t2.key.camelot}")

    try:
        ref_bpm = float(np.median([pair.t1.bpm, pair.t2.bpm]))

        # ── Phase 1+2: plan ───────────────────────────────────────────────
        print("  [1/5] Planning transition...")
        window = select_transition_window(pair.t1, pair.t2, MODEL)
        t1_zone = _zone(pair.t1.file, pair.t1.bpm, pair.t1.first_downbeat_s,
                        max(0, window["t1_exit_bar"] - 8), 24)
        t2_zone = _zone(pair.t2.file, pair.t2.bpm, pair.t2.first_downbeat_s,
                        max(0, window["t2_enter_bar"]), 24)
        script = plan_transition(pair.t1, pair.t2, t1_zone, t2_zone, window, MODEL)
        script = normalize(script)

        # Extract key timing from the normalised script
        fade_in_action  = next((a for a in script.actions if a.type == "fade_in"),  None)
        fade_out_action = next((a for a in script.actions if a.type == "fade_out"), None)
        bass_swap_action = next((a for a in script.actions if a.type == "bass_swap"), None)
        play_t2_action  = next((a for a in script.actions
                                if a.type == "play" and a.track == "T2"), None)

        fade_in_bar    = fade_in_action.start_bar   if fade_in_action  else 0
        fade_in_dur    = fade_in_action.duration_bars if fade_in_action  else 16
        fade_out_bar   = fade_out_action.start_bar  if fade_out_action else fade_in_bar
        fade_out_dur   = fade_out_action.duration_bars if fade_out_action else 16
        bass_swap_bar  = bass_swap_action.at_bar if bass_swap_action and bass_swap_action.at_bar else None
        play_t2_bar    = play_t2_action.at_bar if play_t2_action else fade_in_bar

        blend_start_bar = max(0, min(fade_in_bar, fade_out_bar) - 8)
        blend_end_bar   = max(fade_in_bar  + (fade_in_dur  or 16),
                              fade_out_bar + (fade_out_dur or 16)) + 8

        analysis["script"] = {
            "reasoning": script.reasoning,
            "actions": [a.__dict__ for a in script.actions],
        }
        analysis["timing"] = {
            "ref_bpm":       ref_bpm,
            "fade_in_bar":   fade_in_bar,
            "fade_in_dur":   fade_in_dur,
            "fade_out_bar":  fade_out_bar,
            "fade_out_dur":  fade_out_dur,
            "bass_swap_bar": bass_swap_bar,
            "render_start_bar": blend_start_bar,
            "render_end_bar":   blend_end_bar,
        }

        # ── Load + stretch ────────────────────────────────────────────────
        print("  [2/5] Loading audio...")
        t1_audio = _load_stretched(pair.t1, ref_bpm)
        t2_audio = _load_stretched(pair.t2, ref_bpm)

        # ── Render ────────────────────────────────────────────────────────
        print("  [3/5] Rendering (mix, T1-solo, T2-solo)...")
        full_loaded = {"T1": t1_audio, "T2": t2_audio}

        mix_seg  = _render_window(script, full_loaded, ref_bpm, blend_start_bar, blend_end_bar)
        t1_seg   = _render_window(_solo_script(script, "T1"), {"T1": t1_audio},
                                  ref_bpm, blend_start_bar, blend_end_bar)
        t2_seg   = _render_window(_solo_script(script, "T2"), {"T2": t2_audio},
                                  ref_bpm, blend_start_bar, blend_end_bar)

        mix_seg.export(str(pair_dir / "mix.wav"),    format="wav")
        t1_seg.export( str(pair_dir / "t1_solo.wav"), format="wav")
        t2_seg.export( str(pair_dir / "t2_solo.wav"), format="wav")

        # ── Analysis ─────────────────────────────────────────────────────
        print("  [4/5] Analysing...")

        render_offset_ms = bars_to_ms(blend_start_bar, ref_bpm)
        fade_in_ms   = bars_to_ms(fade_in_bar,  ref_bpm) - render_offset_ms
        fade_in_end  = fade_in_ms  + bars_to_ms(fade_in_dur  or 16, ref_bpm)
        fade_out_ms  = bars_to_ms(fade_out_bar, ref_bpm) - render_offset_ms
        fade_out_end = fade_out_ms + bars_to_ms(fade_out_dur or 16, ref_bpm)
        bass_ms      = (bars_to_ms(bass_swap_bar, ref_bpm) - render_offset_ms
                        if bass_swap_bar is not None else None)

        t1_profile  = _rms_profile(t1_seg)
        t2_profile  = _rms_profile(t2_seg)
        mix_profile = _rms_profile(mix_seg)

        t1_bar_rms  = _bar_rms(t1_profile,  blend_start_bar, ref_bpm)
        t2_bar_rms  = _bar_rms(t2_profile,  blend_start_bar, ref_bpm)
        mix_bar_rms = _bar_rms(mix_profile, blend_start_bar, ref_bpm)

        fade_out_check = _check_fade(t1_bar_rms, fade_out_bar, fade_out_bar + (fade_out_dur or 16), "down")
        fade_in_check  = _check_fade(t2_bar_rms, fade_in_bar,  fade_in_bar  + (fade_in_dur  or 16), "up")
        snap_back      = _check_snap_back(t1_profile, fade_out_end)
        energy_holes   = _check_energy_holes(mix_profile)
        clipping       = _check_clipping(mix_seg)
        bass_transfer  = _check_bass_transfer(mix_seg, bass_ms, ref_bpm)

        analysis["checks"] = {
            "fade_out": {"ok": fade_out_check.ok,
                         "trend_ok": fade_out_check.trend_ok,
                         "start_db": fade_out_check.start_db,
                         "end_db":   fade_out_check.end_db,
                         "total_delta_db": fade_out_check.total_delta_db,
                         "extended_reversals": fade_out_check.extended_reversals},
            "fade_in":  {"ok": fade_in_check.ok,
                         "trend_ok": fade_in_check.trend_ok,
                         "start_db": fade_in_check.start_db,
                         "end_db":   fade_in_check.end_db,
                         "total_delta_db": fade_in_check.total_delta_db,
                         "extended_reversals": fade_in_check.extended_reversals},
            "snap_back":    snap_back,
            "energy_holes": energy_holes,
            "clipping":     clipping,
            "bass_transfer": bass_transfer,
        }

        # ── Build findings list ───────────────────────────────────────────
        if not fade_out_check.trend_ok:
            findings.append(
                f"FAIL  fade_out wrong direction or too shallow: T1 "
                f"{fade_out_check.start_db:.1f}→{fade_out_check.end_db:.1f} dBFS "
                f"(Δ={fade_out_check.total_delta_db:.1f} dB, need ≤-6)"
            )
        elif fade_out_check.extended_reversals:
            findings.append(
                f"WARN  fade_out has {len(fade_out_check.extended_reversals)} extended reversal(s): "
                f"T1 {fade_out_check.start_db:.1f}→{fade_out_check.end_db:.1f} dBFS"
            )
        else:
            findings.append(
                f"PASS  fade_out: T1 {fade_out_check.start_db:.1f}→{fade_out_check.end_db:.1f} dBFS "
                f"(Δ={fade_out_check.total_delta_db:.1f} dB)"
            )

        if not fade_in_check.trend_ok:
            findings.append(
                f"FAIL  fade_in wrong direction or too shallow: T2 "
                f"{fade_in_check.start_db:.1f}→{fade_in_check.end_db:.1f} dBFS "
                f"(Δ={fade_in_check.total_delta_db:.1f} dB, need ≥+6)"
            )
        elif fade_in_check.extended_reversals:
            findings.append(
                f"WARN  fade_in has {len(fade_in_check.extended_reversals)} extended reversal(s): "
                f"T2 {fade_in_check.start_db:.1f}→{fade_in_check.end_db:.1f} dBFS"
            )
        else:
            findings.append(
                f"PASS  fade_in: T2 {fade_in_check.start_db:.1f}→{fade_in_check.end_db:.1f} dBFS "
                f"(Δ={fade_in_check.total_delta_db:.1f} dB)"
            )

        if not snap_back["ok"]:
            findings.append(
                f"FAIL  T1 snap-back: {len(snap_back['snap_frames'])} frame(s) above "
                f"{SNAP_BACK_THRESH_DB} dBFS after fade_out end"
            )
        else:
            findings.append("PASS  no T1 snap-back after fade_out")

        if not energy_holes["ok"]:
            for h in energy_holes["holes"][:3]:
                findings.append(
                    f"WARN  energy hole: {h['length_ms']}ms of near-silence at frame {h['start_frame']}"
                )
        else:
            findings.append("PASS  no energy holes in mix")

        if not clipping["ok"]:
            findings.append(f"WARN  clipping: {clipping['clip_samples']} clipped samples in mix")
        else:
            findings.append("PASS  no clipping")

        if bass_transfer["ok"] is True:
            findings.append(
                f"PASS  bass swap: mix bass pre={bass_transfer['pre_swap_db']:.1f} "
                f"post={bass_transfer['post_swap_db']:.1f} dBFS "
                f"(Δ={bass_transfer['delta_db']:.1f} dB, no sudden drop)"
            )
        elif bass_transfer["ok"] is False:
            findings.append(
                f"FAIL  bass swap: mix bass pre={bass_transfer['pre_swap_db']:.1f} "
                f"post={bass_transfer['post_swap_db']:.1f} dBFS "
                f"(Δ={bass_transfer['delta_db']:.1f} dB, sudden_drop={bass_transfer['sudden_drop']})"
            )
        else:
            findings.append(f"INFO  {bass_transfer.get('note', 'bass_swap skipped')}")

        # ── Write report.txt ─────────────────────────────────────────────
        print("  [5/5] Writing report...")
        markers = {}
        if fade_out_bar is not None:
            markers[fade_out_bar] = "fade_out START"
            markers[fade_out_bar + (fade_out_dur or 16)] = "fade_out END"
        if fade_in_bar is not None:
            markers[fade_in_bar]  = "fade_in START"
            markers[fade_in_bar  + (fade_in_dur  or 16)] = "fade_in END"
        if bass_swap_bar:
            markers[bass_swap_bar] = "bass_swap"

        with open(pair_dir / "report.txt", "w") as f:
            f.write(f"PAIR {idx+1}: {pair.t1.title}  →  {pair.t2.title}\n")
            f.write(f"  T1: {pair.t1.bpm:.1f} BPM  {pair.t1.key.camelot}  file: {Path(pair.t1.file).name}\n")
            f.write(f"  T2: {pair.t2.bpm:.1f} BPM  {pair.t2.key.camelot}  file: {Path(pair.t2.file).name}\n")
            f.write(f"  ref_bpm={ref_bpm:.1f}  render bars {blend_start_bar}–{blend_end_bar}\n\n")
            f.write("SCRIPT REASONING:\n")
            f.write(f"  {script.reasoning}\n\n")
            f.write("SCRIPT ACTIONS:\n")
            for a in script.actions:
                f.write(f"  {a.type:12s}  track={a.track}")
                for k, v in a.__dict__.items():
                    if k in ("type", "track") or v is None:
                        continue
                    f.write(f"  {k}={v}")
                f.write("\n")
            f.write("\nFINDINGS:\n")
            for line in findings:
                f.write(f"  {line}\n")
            f.write(_ascii_graph(t1_bar_rms,  "T1-solo RMS", markers))
            f.write(_ascii_graph(t2_bar_rms,  "T2-solo RMS", markers))
            f.write(_ascii_graph(mix_bar_rms, "Mix RMS",     markers))

        with open(pair_dir / "analysis.json", "w") as f:
            json.dump(analysis, f, indent=2, default=str)

    except Exception:
        error = traceback.format_exc()
        findings.append(f"ERROR: {error}")
        (pair_dir / "error.txt").write_text(error)

    duration_s = time.monotonic() - t_start
    overall_ok = error is None and all(
        not f.startswith("FAIL") for f in findings
    )

    for f in findings:
        status = "  ✓" if f.startswith("PASS") else ("  ✗" if f.startswith("FAIL") else "  ~")
        print(f"{status} {f}")

    return PairResult(
        pair_id=pair_id,
        t1_title=pair.t1.title,
        t2_title=pair.t2.title,
        ok=overall_ok,
        findings=findings,
        error=error,
        duration_s=duration_s,
        analysis=analysis,
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output: {OUT_DIR}")
    print(f"Loading library...")
    analyses = _load_analyses()
    print(f"  {len(analyses)} tracks loaded")

    pairs = _build_pairs(analyses)
    if not pairs:
        print("ERROR: no valid pairs found")
        sys.exit(1)
    print(f"  {len(pairs)} pairs selected (max={MAX_PAIRS})")

    results: list[PairResult] = []
    for i, pair in enumerate(pairs):
        result = _run_pair(pair, i)
        results.append(result)

    # ── Summary ───────────────────────────────────────────────────────────
    summary_lines = [
        f"Audio Simulation Summary — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  {sum(r.ok for r in results)}/{len(results)} pairs PASS",
        "",
        f"  {'#':<4} {'T1→T2':<42} {'Time':>6}  {'Result':<8}",
        f"  {'─'*4} {'─'*42} {'─'*6}  {'─'*8}",
    ]
    for i, r in enumerate(results):
        label = f"{r.t1_title[:18]}→{r.t2_title[:18]}"
        status = "PASS" if r.ok else ("ERROR" if r.error else "FAIL")
        summary_lines.append(f"  {i+1:<4} {label:<42} {r.duration_s:>5.0f}s  {status}")
        for f in r.findings:
            if not f.startswith("PASS"):
                summary_lines.append(f"       {f}")

    summary_lines.append("")
    summary_lines.append("Per-pair outputs:")
    for r in results:
        summary_lines.append(f"  {OUT_DIR / r.pair_id}/")
    summary_lines.append("")

    summary_text = "\n".join(summary_lines)
    print(f"\n{'='*60}")
    print(summary_text)
    (OUT_DIR / "summary.txt").write_text(summary_text)
    print(f"\nDone. Results in: {OUT_DIR}")


if __name__ == "__main__":
    main()
