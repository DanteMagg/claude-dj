#!/usr/bin/env python3
"""
Simulate DJ transitions from the house track library and capture detailed logs.

Pipeline per pair:
  1. Load cached analyses from library.json
  2. select_transition_window (Phase 1)
  3. plan_transition (Phase 2)
  4. normalize()
  5. Post-validate the mix script against a checklist
  6. Write per-pair log + summary report
  7. (optional) Spot-render the transition window to a short WAV for listening

Usage:
  cd "/Users/DantesFolder/Claude DJ"
  python3 scripts/simulate_transitions.py [--spot-render] [--pairs N]

  --spot-render   Render ±8 bars around each transition window to a WAV file.
                  This is the correct way to evaluate audio quality; script
                  validation alone cannot catch rendering or gain-ramp bugs.
  --pairs N       Override MAX_PAIRS (default 12).

Output:
  simulate_runs/<timestamp>/  — one .log per pair + summary.txt
  simulate_runs/<timestamp>/spot_renders/  — short WAV files (with --spot-render)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "claude-dj"))

from schema import MixScript, TrackAnalysis
from mix_director import select_transition_window, plan_transition, _camelot_distance
from normalizer import normalize

# ── API key ───────────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load .env from claude-dj/ if ANTHROPIC_API_KEY not already set."""
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
        print("ERROR: ANTHROPIC_API_KEY not found in environment or claude-dj/.env")
        sys.exit(1)

_load_env()

# ── CLI args ─────────────────────────────────────────────────────────────────

import argparse as _argparse
_ap = _argparse.ArgumentParser(add_help=True)
_ap.add_argument("--spot-render", action="store_true",
                 help="Render ±8 bars around each transition window to WAV")
_ap.add_argument("--pairs", type=int, default=None,
                 help="Override MAX_PAIRS")
_CLI = _ap.parse_args()

# ── Constants ────────────────────────────────────────────────────────────────

MODEL        = "claude-haiku-4-5-20251001"   # cheap for simulation; swap to sonnet for fidelity
LIBRARY_PATH = PROJECT_ROOT / "claude-dj" / "cache" / "library.json"
CACHE_DIR    = PROJECT_ROOT / "claude-dj" / "cache"
OUT_DIR      = PROJECT_ROOT / "simulate_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")

BPM_LOW  = 118
BPM_HIGH = 135
MAX_PAIRS    = _CLI.pairs if _CLI.pairs else 12
PAIRS_PER_BUCKET = max(1, MAX_PAIRS // 4)

# ── Logging setup ────────────────────────────────────────────────────────────

def _build_pair_logger(name: str, log_path: Path) -> tuple[logging.Logger, logging.FileHandler]:
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(name)-18s  %(levelname)-7s  %(message)s",
                            datefmt="%H:%M:%S")
    fh.setFormatter(fmt)
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh)
    return log, fh


def _configure_global_debug(fh: logging.FileHandler) -> None:
    """Route mix_director and normalizer loggers to the current pair's file handler."""
    for name in ("mix_director", "normalizer"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        # Remove stale handlers from previous pairs
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(fh)
        lg.propagate = False


# ── Library loading ──────────────────────────────────────────────────────────

def _load_analyses() -> list[TrackAnalysis]:
    """Load TrackAnalysis objects from library.json + per-track analysis.json cache."""
    from analyze import analyze_track   # local import; uses librosa

    lib = json.loads(LIBRARY_PATH.read_text())
    analyses: list[TrackAnalysis] = []

    for track_hash, meta in lib.items():
        path = meta.get("path", "")
        if not path.endswith(".mp3"):
            continue
        bpm = meta.get("bpm", 0)
        if not (BPM_LOW <= bpm <= BPM_HIGH):
            continue
        camelot = meta.get("key_camelot", "")
        if not camelot:
            continue
        if not Path(path).exists():
            continue

        cache_file = CACHE_DIR / track_hash / "analysis.json"
        if not cache_file.exists():
            continue

        try:
            ta = analyze_track(path, track_hash, no_stems=True)
            analyses.append(ta)
        except Exception as exc:
            print(f"  SKIP {Path(path).name}: {exc}")

    return analyses


# ── Pair selection ───────────────────────────────────────────────────────────

@dataclass
class Pair:
    t1: TrackAnalysis
    t2: TrackAnalysis
    camelot_dist: int
    bpm_delta: float


def _build_pairs(tracks: list[TrackAnalysis]) -> list[Pair]:
    """
    Build all unique adjacent-key pairs (Camelot dist ≤ 1).
    Sort: same-key first, then ±1; within each group by BPM proximity.
    """
    pairs: list[Pair] = []
    seen: set[tuple[str, str]] = set()

    for i, t1 in enumerate(tracks):
        for t2 in tracks:
            if t1 is t2:
                continue
            k1 = getattr(t1.key, "camelot", "")
            k2 = getattr(t2.key, "camelot", "")
            key = (t1.id, t2.id)
            if key in seen:
                continue
            seen.add(key)
            seen.add((t2.id, t1.id))

            dist = _camelot_distance(k1, k2)
            if dist > 1:
                continue

            pairs.append(Pair(
                t1=t1, t2=t2,
                camelot_dist=dist,
                bpm_delta=abs(t1.bpm - t2.bpm),
            ))

    pairs.sort(key=lambda p: (p.camelot_dist, p.bpm_delta))
    # 4-bucket balanced coverage: (dist=0|1) × (same-BPM|cross-BPM)
    d0_same  = [p for p in pairs if p.camelot_dist == 0 and p.bpm_delta == 0][:PAIRS_PER_BUCKET]
    d0_cross = [p for p in pairs if p.camelot_dist == 0 and p.bpm_delta > 0][:PAIRS_PER_BUCKET]
    d1_same  = [p for p in pairs if p.camelot_dist == 1 and p.bpm_delta == 0][:PAIRS_PER_BUCKET]
    d1_cross = [p for p in pairs if p.camelot_dist == 1 and p.bpm_delta > 0][:PAIRS_PER_BUCKET]
    selected = d0_same + d0_cross + d1_same + d1_cross
    return selected[:MAX_PAIRS]


# ── Post-validation ──────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    severity: str    # ERROR | WARNING | INFO
    rule: str
    detail: str


def validate_script(script: MixScript) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    actions = script.actions
    tracks  = script.tracks
    non_final_ids = {t.id for t in tracks[:-1]}

    # ── Rule 1: every non-final track must have fade_out
    for tid in non_final_ids:
        if not any(a.type == "fade_out" and a.track == tid for a in actions):
            issues.append(ValidationIssue(
                "ERROR", "missing_fade_out",
                f"{tid} has no fade_out — will play to file end before T2 starts",
            ))

    # ── Rule 2: every fade_in must have a following play
    for fi in (a for a in actions if a.type == "fade_in"):
        fade_end = (fi.start_bar or 0) + (fi.duration_bars or 0)
        has_play = any(
            a.type == "play" and a.track == fi.track and (a.at_bar or 0) >= fade_end
            for a in actions
        )
        if not has_play:
            issues.append(ValidationIssue(
                "ERROR", "orphaned_fade_in",
                f"{fi.track} fade_in(start={fi.start_bar}, dur={fi.duration_bars}) "
                f"has no play at bar {fade_end}",
            ))

    # ── Rule 3: play.from_bar must match fade_in.from_bar + duration_bars
    for fi in (a for a in actions if a.type == "fade_in"):
        fade_end     = (fi.start_bar or 0) + (fi.duration_bars or 0)
        correct_from = (fi.from_bar or 0) + (fi.duration_bars or 0)
        following = [
            a for a in actions
            if a.type == "play" and a.track == fi.track and (a.at_bar or 0) >= fade_end
        ]
        if following:
            pl = min(following, key=lambda a: a.at_bar or 0)
            if pl.at_bar != fade_end:
                issues.append(ValidationIssue(
                    "ERROR", "play_at_bar_mismatch",
                    f"{fi.track} play.at_bar={pl.at_bar} should be {fade_end} "
                    f"(fade_in.start_bar={fi.start_bar} + duration_bars={fi.duration_bars})",
                ))
            if pl.from_bar != correct_from:
                issues.append(ValidationIssue(
                    "WARNING", "play_from_bar_wrong",
                    f"{fi.track} play.from_bar={pl.from_bar} should be {correct_from} "
                    f"(fade_in.from_bar={fi.from_bar} + duration_bars={fi.duration_bars}) "
                    "— normalizer corrects this, but Claude should get it right",
                ))

    # ── Rule 4: every blend transition must have a bass_swap
    fade_ins  = [a for a in actions if a.type == "fade_in"]
    fade_outs = [a for a in actions if a.type == "fade_out"]
    for fi in fade_ins:
        fi_start = fi.start_bar or 0
        fi_end   = fi_start + (fi.duration_bars or 0)
        has_swap = any(
            a.type == "bass_swap"
            and a.track != fi.track
            and fi_start <= (a.at_bar or 0) <= fi_end
            for a in actions
        )
        if not has_swap:
            issues.append(ValidationIssue(
                "WARNING", "missing_bass_swap",
                f"no bass_swap found during {fi.track} fade_in window ({fi_start}–{fi_end})",
            ))

    # ── Rule 5: bass_swap must include incoming_track
    for a in (x for x in actions if x.type == "bass_swap"):
        if not a.incoming_track:
            issues.append(ValidationIssue(
                "ERROR", "bass_swap_missing_incoming",
                f"bass_swap(track={a.track}, at_bar={a.at_bar}) missing incoming_track field — "
                "T2 bass stem overlay will be skipped",
            ))

    # ── Rule 6: bass_swap.at_bar must be multiple of 8
    for a in (x for x in actions if x.type == "bass_swap"):
        bar = a.at_bar or 0
        if bar % 8 != 0:
            issues.append(ValidationIssue(
                "WARNING", "bass_swap_not_phrase_aligned",
                f"bass_swap(track={a.track}) at_bar={bar} is not a multiple of 8",
            ))

    # ── Rule 7: T1 fade_out must start inside the blend window
    for fo in (a for a in actions if a.type == "fade_out" and a.track in non_final_ids):
        fo_start = fo.start_bar or 0
        # find the corresponding fade_in
        fi_list = [a for a in actions if a.type == "fade_in" and a.track != fo.track]
        if fi_list:
            fi = min(fi_list, key=lambda a: a.start_bar or 0)
            fi_start = fi.start_bar or 0
            if fo_start > (fi_start + (fi.duration_bars or 0)):
                issues.append(ValidationIssue(
                    "WARNING", "fade_out_after_blend_window",
                    f"T1 fade_out starts at bar {fo_start} which is after T2 blend window ends "
                    f"({fi_start + (fi.duration_bars or 0)}) — T1 will play over T2 at full volume",
                ))
            if fo_start < fi_start - 4:
                issues.append(ValidationIssue(
                    "WARNING", "fade_out_before_fade_in",
                    f"T1 fade_out(bar={fo_start}) starts before T2 fade_in(bar={fi_start}) — "
                    "there will be a gap of silence",
                ))

    # ── Rule 8: no action references bars beyond track length
    track_bars = {t.id: None for t in tracks}  # can't know without analysis; skipped in this pass

    # ── Rule 9: duplicate action types for same track
    from collections import Counter
    type_track = Counter((a.type, a.track) for a in actions)
    for (atype, tid), count in type_track.items():
        if atype == "fade_out" and count > 1:
            issues.append(ValidationIssue(
                "WARNING", "duplicate_fade_out",
                f"{tid} has {count} fade_out actions — only the first will apply",
            ))
        if atype == "bass_swap" and count > 1 and tid in non_final_ids:
            issues.append(ValidationIssue(
                "INFO", "multiple_bass_swaps",
                f"{tid} has {count} bass_swap actions",
            ))

    # ── Rule 10: reasoning quality checks
    reasoning = script.reasoning or ""
    if len(reasoning) < 40:
        issues.append(ValidationIssue(
            "WARNING", "thin_reasoning",
            f"reasoning is very short ({len(reasoning)} chars) — Claude may not be "
            "citing specific cue points",
        ))
    import re as _re
    _keyword_checks = {
        "bar":     [r"\bbar\b"],
        "bpm":     [r"\bbpm\b"],
        "key":     [r"\bkey\b", r"\b\d{1,2}[AB]\b"],  # "key" OR Camelot notation e.g. "7B"
        "camelot": [r"\bcamelot\b", r"\b\d{1,2}[AB]\b"],  # word OR notation
        "bass":    [r"\bbass\b"],
    }
    for keyword, patterns in _keyword_checks.items():
        if not any(_re.search(p, reasoning, _re.IGNORECASE) for p in patterns):
            issues.append(ValidationIssue(
                "INFO", "reasoning_missing_keyword",
                f"reasoning doesn't mention '{keyword}' — may lack specificity",
            ))

    return issues


# ── Spot-render ──────────────────────────────────────────────────────────────

def spot_render(
    pair: "Pair",
    script: MixScript,
    out_path: Path,
    log: logging.Logger,
) -> None:
    """
    Render ±8 bars around the transition window to a short WAV.
    This is the primary tool for evaluating audio quality; script
    validation alone cannot catch bugs in the gain ramp, EQ application,
    or stem mixing.

    Window: (fade_in.start_bar - 8) to (play(T2).at_bar + 8), clamped to [0, ∞).
    Both tracks are loaded and time-stretched to ref_bpm (median of T1/T2).
    """
    try:
        from executor import bars_to_ms, load_track, time_stretch, render_chunk, _apply_soft_limiter
        from pydub import AudioSegment
        import numpy as np

        ref_bpm = float(np.median([pair.t1.bpm, pair.t2.bpm]))

        # Determine the render window
        fade_in_bar  = next(
            (a.start_bar or 0 for a in script.actions if a.type == "fade_in"), 0
        )
        play_t2_bar  = next(
            (a.at_bar or 0 for a in script.actions if a.type == "play" and a.track == "T2"), fade_in_bar + 32
        )
        fade_out_bar = next(
            (a.start_bar or 0 for a in script.actions if a.type == "fade_out"), fade_in_bar
        )
        # Include 8 bars of T1 before the fade starts and 8 bars of T2 after play fires
        render_start_bar = max(0, min(fade_in_bar, fade_out_bar) - 8)
        render_end_bar   = play_t2_bar + 8

        start_ms = bars_to_ms(render_start_bar, ref_bpm)
        end_ms   = bars_to_ms(render_end_bar,   ref_bpm)
        total_ms = end_ms - start_ms

        log.info(
            "Spot-render: bars %d–%d  (%.1fs)  ref_bpm=%.1f",
            render_start_bar, render_end_bar, total_ms / 1000, ref_bpm,
        )

        # Load and time-stretch tracks
        def _load(ta: "TrackAnalysis") -> AudioSegment:
            seg = load_track(ta.file)
            fdb = int(ta.first_downbeat_s * 1000)
            if fdb > 0:
                seg = seg[fdb:]
            return time_stretch(seg, ta.bpm, ref_bpm)

        loaded = {
            "T1": _load(pair.t1),
            "T2": _load(pair.t2),
        }
        target_rate = loaded["T1"].frame_rate
        for tid in loaded:
            if loaded[tid].frame_rate != target_rate:
                loaded[tid] = loaded[tid].set_frame_rate(target_rate)

        # Render in 1-bar chunks and concatenate
        chunk_ms  = bars_to_ms(1, ref_bpm)
        canvas    = AudioSegment.silent(duration=0, frame_rate=target_rate)
        for bar in range(render_start_bar, render_end_bar):
            bar_ms = bars_to_ms(bar, ref_bpm)
            chunk  = render_chunk(script, loaded, {}, ref_bpm, bar_ms, chunk_ms)
            canvas = canvas + chunk

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.export(str(out_path), format="wav")
        log.info("Spot-render saved: %s  (%.1fs)", out_path.name, len(canvas) / 1000)

    except Exception as exc:
        log.warning("Spot-render failed: %s", exc)


# ── Per-pair runner ──────────────────────────────────────────────────────────

@dataclass
class PairResult:
    pair: Pair
    window: Optional[dict]
    script: Optional[MixScript]
    norm_script: Optional[MixScript]
    issues: list[ValidationIssue]
    error: Optional[str]
    duration_s: float


def run_pair(pair: Pair, log: logging.Logger) -> PairResult:
    t1, t2 = pair.t1, pair.t2
    k1 = getattr(t1.key, "camelot", "?")
    k2 = getattr(t2.key, "camelot", "?")

    log.info("=" * 72)
    log.info(
        "PAIR: %r → %r",
        getattr(t1, "title", t1.file),
        getattr(t2, "title", t2.file),
    )
    log.info(
        "  T1: %.1f BPM  %s (%s)  %d bars  file: %s",
        t1.bpm, k1, getattr(t1.key, "standard", ""), t1.bar_grid.n_bars,
        Path(t1.file).name,
    )
    log.info(
        "  T2: %.1f BPM  %s (%s)  %d bars  file: %s",
        t2.bpm, k2, getattr(t2.key, "standard", ""), t2.bar_grid.n_bars,
        Path(t2.file).name,
    )
    log.info(
        "  Camelot dist=%d  BPM delta=%.1f",
        pair.camelot_dist, pair.bpm_delta,
    )

    t_start = time.monotonic()
    window = None
    script = None
    norm_script = None
    issues: list[ValidationIssue] = []
    error: Optional[str] = None

    try:
        # ── Phase 1: window selection ─────────────────────────────────────
        log.info("--- Phase 1: select_transition_window ---")
        window = select_transition_window(t1, t2, MODEL)
        log.info(
            "Window: t1_exit=%d  t2_enter=%d  overlap=%d  style=%s",
            window["t1_exit_bar"], window["t2_enter_bar"],
            window["window_bars"], window["style"],
        )

        # ── Phase 2: zone analysis + planning ────────────────────────────
        log.info("--- Phase 2: plan_transition ---")
        from analyze import analyze_transition_zone as _zone
        t1_zone = _zone(
            t1.file, t1.bpm, t1.first_downbeat_s,
            max(0, window["t1_exit_bar"] - 8), 24,
        )
        t2_zone = _zone(
            t2.file, t2.bpm, t2.first_downbeat_s,
            max(0, window["t2_enter_bar"]), 24,
        )

        script = plan_transition(t1, t2, t1_zone, t2_zone, window, MODEL)
        log.info("Script received: %d actions", len(script.actions))
        log.info("Reasoning: %s", script.reasoning)
        log.info("Actions (pre-normalize):")
        for a in script.actions:
            log.info("  %s", json.dumps(a.__dict__, default=str, separators=(",", ":")))

        # ── Normalize ─────────────────────────────────────────────────────
        log.info("--- Normalizer ---")
        norm_script = normalize(script)
        added = [a for a in norm_script.actions if a not in script.actions]
        if added:
            log.info("Normalizer injected %d action(s):", len(added))
            for a in added:
                log.info("  + %s", json.dumps(a.__dict__, default=str, separators=(",", ":")))
        else:
            log.info("Normalizer: no injections needed (script was clean)")

        # ── Validate ──────────────────────────────────────────────────────
        log.info("--- Validation ---")
        issues = validate_script(norm_script)
        if not issues:
            log.info("PASS — no issues found")
        else:
            for iss in issues:
                lvl = {"ERROR": log.error, "WARNING": log.warning, "INFO": log.info}.get(
                    iss.severity, log.info
                )
                lvl("[%s] %s: %s", iss.severity, iss.rule, iss.detail)

        # ── Spot-render (optional) ─────────────────────────────────────────
        if _CLI.spot_render and norm_script is not None:
            log.info("--- Spot-render ---")
            render_dir = OUT_DIR / "spot_renders"
            t1_stem = Path(pair.t1.file).stem[:20]
            t2_stem = Path(pair.t2.file).stem[:20]
            safe_name  = f"{t1_stem}__{t2_stem}.wav"
            spot_render(pair, norm_script, render_dir / safe_name, log)

    except Exception as exc:
        error = traceback.format_exc()
        log.error("EXCEPTION: %s\n%s", exc, error)

    duration_s = time.monotonic() - t_start
    log.info("Pair completed in %.1fs", duration_s)

    return PairResult(
        pair=pair,
        window=window,
        script=script,
        norm_script=norm_script,
        issues=issues,
        error=error,
        duration_s=duration_s,
    )


# ── Summary report ───────────────────────────────────────────────────────────

def write_summary(results: list[PairResult], out_dir: Path) -> None:
    lines = [
        "=" * 72,
        f"SIMULATION SUMMARY  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Model: {MODEL}  Pairs: {len(results)}",
        "=" * 72,
        "",
    ]

    total_errors   = 0
    total_warnings = 0
    total_injected = 0

    for i, r in enumerate(results, 1):
        t1, t2 = r.pair.t1, r.pair.t2
        k1 = getattr(t1.key, "camelot", "?")
        k2 = getattr(t2.key, "camelot", "?")

        if r.error:
            status = "CRASH"
        elif any(iss.severity == "ERROR" for iss in r.issues):
            status = "ERRORS"
        elif any(iss.severity == "WARNING" for iss in r.issues):
            status = "WARNINGS"
        else:
            status = "CLEAN"

        lines.append(
            f"[{i:2d}] {status:8s}  {k1}→{k2} (dist={r.pair.camelot_dist})  "
            f"{t1.bpm:.0f}→{t2.bpm:.0f} BPM  "
            f"{Path(t1.file).stem[:28]} → {Path(t2.file).stem[:28]}"
        )

        if r.window:
            lines.append(
                f"         Window: exit=b{r.window['t1_exit_bar']}  "
                f"enter=b{r.window['t2_enter_bar']}  "
                f"overlap={r.window['window_bars']}bars  style={r.window['style']}"
            )

        if r.script:
            lines.append(f"         Reasoning: {r.script.reasoning[:120]}")

        if r.norm_script:
            injected = [a for a in r.norm_script.actions if a not in (r.script.actions if r.script else [])]
            if injected:
                total_injected += len(injected)
                lines.append(f"         Normalizer injected: {[a.type+'('+a.track+')' for a in injected]}")

        for iss in r.issues:
            lines.append(f"         [{iss.severity}] {iss.rule}: {iss.detail}")
            if iss.severity == "ERROR":   total_errors += 1
            if iss.severity == "WARNING": total_warnings += 1

        if r.error:
            lines.append(f"         ERROR: {r.error.splitlines()[-1]}")

        lines.append(f"         Duration: {r.duration_s:.1f}s")
        lines.append("")

    lines += [
        "=" * 72,
        "TOTALS",
        f"  Pairs:    {len(results)}",
        f"  Clean:    {sum(1 for r in results if not r.error and not any(i.severity in ('ERROR','WARNING') for i in r.issues))}",
        f"  Warnings: {total_warnings}",
        f"  Errors:   {total_errors}",
        f"  Crashes:  {sum(1 for r in results if r.error)}",
        f"  Normalizer injections total: {total_injected}",
        "",
        "INJECTION BREAKDOWN (normalizer had to fix Claude's output):",
    ]

    inj_types: dict[str, int] = {}
    for r in results:
        if r.script and r.norm_script:
            for a in r.norm_script.actions:
                if a not in r.script.actions:
                    inj_types[a.type] = inj_types.get(a.type, 0) + 1
    for t, c in sorted(inj_types.items(), key=lambda x: -x[1]):
        lines.append(f"  {t}: {c}")

    lines += [
        "",
        "ISSUE BREAKDOWN:",
    ]
    all_issues = [i for r in results for i in r.issues]
    rule_counts: dict[str, int] = {}
    for iss in all_issues:
        rule_counts[iss.rule] = rule_counts.get(iss.rule, 0) + 1
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rule}: {count}")

    summary_path = out_dir / "summary.txt"
    summary_path.write_text("\n".join(lines) + "\n")
    print(f"\n{'='*72}")
    print("\n".join(lines))
    print(f"\nFull logs: {out_dir}/")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Console handler for top-level sim logger
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S"))
    root_log = logging.getLogger("sim")
    root_log.setLevel(logging.INFO)
    root_log.addHandler(ch)

    root_log.info("Loading library analyses (BPM %d–%d)...", BPM_LOW, BPM_HIGH)
    analyses = _load_analyses()
    root_log.info("Loaded %d tracks", len(analyses))
    for a in sorted(analyses, key=lambda x: x.bpm):
        root_log.info(
            "  %.1f BPM  %-4s  %s",
            a.bpm, getattr(a.key, "camelot", "?"), Path(a.file).name[:60],
        )

    root_log.info("Building adjacent-key pairs (Camelot dist ≤ 1)...")
    pairs = _build_pairs(analyses)
    root_log.info("Selected %d pairs (capped at %d)", len(pairs), MAX_PAIRS)
    for i, p in enumerate(pairs, 1):
        root_log.info(
            "  [%2d] dist=%d  %s→%s  %.1f→%.1f BPM  %s → %s",
            i, p.camelot_dist,
            getattr(p.t1.key, "camelot", "?"),
            getattr(p.t2.key, "camelot", "?"),
            p.t1.bpm, p.t2.bpm,
            Path(p.t1.file).stem[:30],
            Path(p.t2.file).stem[:30],
        )

    results: list[PairResult] = []
    for i, pair in enumerate(pairs, 1):
        t1_name = Path(pair.t1.file).stem[:30]
        t2_name = Path(pair.t2.file).stem[:30]
        log_name = f"{i:02d}_{t1_name[:20]}__{t2_name[:20]}".replace(" ", "_").replace("/", "-")
        log_path = OUT_DIR / f"{log_name}.log"

        root_log.info("\n[%d/%d] %s → %s", i, len(pairs), t1_name, t2_name)

        pair_log, fh = _build_pair_logger(f"sim.pair{i}", log_path)
        _configure_global_debug(fh)   # route mix_director + normalizer DEBUG into this file

        result = run_pair(pair, pair_log)
        results.append(result)

        # Detach file handler so next pair gets its own file
        pair_log.removeHandler(fh)
        for name in ("mix_director", "normalizer"):
            logging.getLogger(name).removeHandler(fh)
        fh.close()

        status = "CLEAN" if not result.error and not any(
            i.severity in ("ERROR", "WARNING") for i in result.issues
        ) else ("CRASH" if result.error else f"{sum(1 for x in result.issues if x.severity=='ERROR')}E {sum(1 for x in result.issues if x.severity=='WARNING')}W")
        root_log.info("  → %s  (%.1fs)", status, result.duration_s)

    write_summary(results, OUT_DIR)


if __name__ == "__main__":
    main()
