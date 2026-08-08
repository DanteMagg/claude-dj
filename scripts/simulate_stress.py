#!/usr/bin/env python3
"""
Stress-test simulations — covers scenarios the main simulate_transitions.py skips:

  Bucket A: Camelot dist=2  (borderline harmonic — needs mid suppression)
  Bucket B: Camelot dist=3+ (incompatible — should force cuts or ≤8-bar blend)
  Bucket C: Large BPM gap >4 BPM, dist≤1  (needs breakdown masking or bridge)
  Bucket D: Cross-BPM range 123→129 or 129→123 with dist≤1  (BPM + harmonic)

Each bucket gets up to PAIRS_PER_BUCKET pairs. Validates technique-appropriate
responses: dist≥2 should use shorter overlap; dist≥3 should use cut or ≤8 bars;
large BPM gaps should show explicit management (breakdown exit, short overlap).

Usage:
  cd /Users/DantesFolder/Claude\ DJ
  python3 scripts/simulate_stress.py
"""
from __future__ import annotations

import json
import logging
import os
import re
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
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

_load_env()

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL        = "claude-haiku-4-5-20251001"
LIBRARY_PATH = PROJECT_ROOT / "claude-dj" / "cache" / "library.json"
CACHE_DIR    = PROJECT_ROOT / "claude-dj" / "cache"
OUT_DIR      = PROJECT_ROOT / "simulate_runs" / ("stress_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

BPM_LOW  = 118
BPM_HIGH = 135
PAIRS_PER_BUCKET = 3   # 4 buckets × 3 = 12 pairs

# ── Logging ───────────────────────────────────────────────────────────────────

def _build_pair_logger(name: str, log_path: Path):
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(name)-18s  %(levelname)-7s  %(message)s",
                            datefmt="%H:%M:%S")
    fh.setFormatter(fmt)
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh)
    return log, fh


def _configure_global_debug(fh) -> None:
    for name in ("mix_director", "normalizer"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(fh)
        lg.propagate = False


# ── Library loading ──────────────────────────────────────────────────────────

def _load_analyses() -> list[TrackAnalysis]:
    from analyze import analyze_track
    lib = json.loads(LIBRARY_PATH.read_text())
    analyses: list[TrackAnalysis] = []
    for track_hash, meta in lib.items():
        path = meta.get("path", "")
        if not path.endswith(".mp3"):
            continue
        bpm = meta.get("bpm", 0)
        if not (BPM_LOW <= bpm <= BPM_HIGH):
            continue
        if not meta.get("key_camelot", ""):
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


# ── Pair selection ────────────────────────────────────────────────────────────

@dataclass
class Pair:
    t1: TrackAnalysis
    t2: TrackAnalysis
    camelot_dist: int
    bpm_delta: float
    bucket: str   # A / B / C / D


def _build_stress_pairs(tracks: list[TrackAnalysis]) -> list[Pair]:
    """
    Build pairs by stress-test bucket:
      A: dist=2 (borderline harmonic — suppress mids)
      B: dist≥3 (incompatible — cut or ≤8-bar blend)
      C: dist≤1 AND bpm_delta > 4 (large BPM gap)
      D: dist≤1 AND bpm_delta > 4 AND bpm crosses 126 boundary (genre-hop)
    """
    all_pairs: list[Pair] = []
    seen: set[tuple[str, str]] = set()

    for t1 in tracks:
        for t2 in tracks:
            if t1 is t2:
                continue
            key = tuple(sorted([t1.id, t2.id]))
            if key in seen:
                continue
            seen.add(key)

            k1 = getattr(t1.key, "camelot", "")
            k2 = getattr(t2.key, "camelot", "")
            dist = _camelot_distance(k1, k2)
            delta = abs(t1.bpm - t2.bpm)

            if dist == 2:
                all_pairs.append(Pair(t1, t2, dist, delta, "A"))
            elif dist >= 3:
                all_pairs.append(Pair(t1, t2, dist, delta, "B"))
            elif dist <= 1 and delta > 4:
                # Bucket C: large BPM gap; Bucket D: also crosses 126 BPM line
                crosses_boundary = (t1.bpm < 126 < t2.bpm) or (t2.bpm < 126 < t1.bpm)
                bucket = "D" if crosses_boundary else "C"
                all_pairs.append(Pair(t1, t2, dist, delta, bucket))

    # Sort within each bucket: prefer pairs closest to threshold (dist=2 over dist=5,
    # smallest BPM gap within C/D, etc.)
    def sort_key(p: Pair):
        if p.bucket == "A":
            return (0, p.bpm_delta)
        if p.bucket == "B":
            return (1, p.camelot_dist, p.bpm_delta)
        if p.bucket == "C":
            return (2, p.bpm_delta)
        return (3, p.bpm_delta)

    all_pairs.sort(key=sort_key)

    buckets: dict[str, list[Pair]] = {b: [] for b in "ABCD"}
    for p in all_pairs:
        if len(buckets[p.bucket]) < PAIRS_PER_BUCKET:
            buckets[p.bucket].append(p)

    selected = buckets["A"] + buckets["B"] + buckets["C"] + buckets["D"]
    return selected


# ── Validation ────────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    severity: str
    rule: str
    detail: str


def validate_script(script: MixScript, pair: Pair) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    actions = script.actions
    tracks  = script.tracks
    non_final_ids = {t.id for t in tracks[:-1]}

    # Standard rules (same as main simulator) ─────────────────────────────────

    for tid in non_final_ids:
        if not any(a.type == "fade_out" and a.track == tid for a in actions):
            issues.append(ValidationIssue("ERROR", "missing_fade_out",
                f"{tid} has no fade_out"))

    for fi in (a for a in actions if a.type == "fade_in"):
        fade_end = (fi.start_bar or 0) + (fi.duration_bars or 0)
        correct_from = (fi.from_bar or 0) + (fi.duration_bars or 0)
        following = [a for a in actions if a.type == "play" and a.track == fi.track
                     and (a.at_bar or 0) >= fade_end]
        if not following:
            issues.append(ValidationIssue("ERROR", "orphaned_fade_in",
                f"{fi.track} fade_in has no following play"))
        else:
            pl = min(following, key=lambda a: a.at_bar or 0)
            if pl.from_bar != correct_from:
                issues.append(ValidationIssue("WARNING", "play_from_bar_wrong",
                    f"{fi.track} play.from_bar={pl.from_bar} should be {correct_from}"))

    fade_ins = [a for a in actions if a.type == "fade_in"]
    for fi in fade_ins:
        fi_start = fi.start_bar or 0
        fi_end   = fi_start + (fi.duration_bars or 0)
        has_swap = any(a.type == "bass_swap" and a.track != fi.track
                       and fi_start <= (a.at_bar or 0) <= fi_end for a in actions)
        if not has_swap:
            issues.append(ValidationIssue("WARNING", "missing_bass_swap",
                f"no bass_swap during {fi.track} fade_in window ({fi_start}–{fi_end})"))

    for a in (x for x in actions if x.type == "bass_swap"):
        if not a.incoming_track:
            issues.append(ValidationIssue("ERROR", "bass_swap_missing_incoming",
                f"bass_swap({a.track}) missing incoming_track"))

    # EQ restore check — T2 non-unity EQ must have a restore ──────────────────
    incoming_tids = {a.track for a in actions if a.type in ("fade_in", "play")}
    outgoing_tids = {a.track for a in actions if a.type == "fade_out"}
    continuing_tids = incoming_tids - outgoing_tids
    for a in (x for x in actions if x.type == "eq" and x.track in continuing_tids):
        non_unity = (
            (a.low is not None and a.low != 1.0) or
            (a.mid is not None and a.mid != 1.0) or
            (a.high is not None and a.high != 1.0)
        )
        if not non_unity:
            continue
        fi = next((x for x in actions if x.type == "fade_in" and x.track == a.track), None)
        blend_end = (fi.start_bar or 0) + (fi.duration_bars or 0) if fi else 0
        has_restore = any(
            x.type == "eq" and x.track == a.track
            and (x.bar or 0) >= blend_end
            and x.low == 1.0 and x.mid == 1.0 and x.high == 1.0
            for x in actions
        )
        if not has_restore:
            issues.append(ValidationIssue("WARNING", "missing_eq_restore",
                f"{a.track} has eq(low={a.low},mid={a.mid},high={a.high}) at bar {a.bar} "
                f"but no restore at/after blend end bar {blend_end} — EQ bleeds into rest of mix"))

    # Stress-test-specific rules ──────────────────────────────────────────────

    # Bucket A / B: dist≥2 should use shorter overlap
    if pair.camelot_dist >= 2:
        for fi in fade_ins:
            dur = fi.duration_bars or 0
            if pair.camelot_dist >= 3 and dur > 8:
                issues.append(ValidationIssue("WARNING", "incompatible_key_overlap_too_long",
                    f"Camelot dist={pair.camelot_dist} but fade_in duration={dur} bars — "
                    f"should be ≤8 bars or a cut; long blend will produce audible clash"))
            elif pair.camelot_dist == 2 and dur > 16:
                issues.append(ValidationIssue("INFO", "borderline_key_overlap_long",
                    f"Camelot dist=2 with {dur}-bar overlap — consider ≤16 bars + mid suppression"))

    # Bucket A: dist=2 should suppress T2 mids during overlap
    if pair.camelot_dist == 2:
        t2_id = tracks[-1].id if tracks else None
        has_mid_suppress = any(
            a.type == "eq" and a.track == t2_id and a.mid is not None and a.mid < 0.8
            for a in actions
        )
        if not has_mid_suppress:
            issues.append(ValidationIssue("INFO", "dist2_no_mid_suppression",
                f"Camelot dist=2 but no eq(T2, mid<0.8) found — "
                f"harmonic clash not managed; section 18.2 of dj_skill.md calls for mid=0.4–0.5"))

    # Bucket B: dist≥3 should use cut (no fade_in) or very short overlap
    if pair.camelot_dist >= 3:
        has_fade_in = any(a.type == "fade_in" for a in actions)
        if has_fade_in:
            fi = next(a for a in actions if a.type == "fade_in")
            dur = fi.duration_bars or 0
            if dur > 8:
                issues.append(ValidationIssue("WARNING", "incompatible_used_long_blend",
                    f"dist={pair.camelot_dist} used {dur}-bar fade_in instead of cut — "
                    f"should be cut or ≤8-bar blend with mids suppressed"))
        else:
            # Check it's a proper cut pattern (fade_out + play, no fade_in)
            has_play = any(a.type == "play" for a in actions)
            if not has_play:
                issues.append(ValidationIssue("ERROR", "no_play_action",
                    "no play action in cut transition"))

    # Bucket C/D: large BPM gap — look for breakdown exit or short overlap
    if pair.bpm_delta > 4 and pair.camelot_dist <= 1:
        # Phase 1 should have picked breakdown or the overlap should be ≤16
        for fi in fade_ins:
            dur = fi.duration_bars or 0
            if dur > 24:
                issues.append(ValidationIssue("WARNING", "large_bpm_gap_long_overlap",
                    f"BPM delta={pair.bpm_delta:.1f} with {dur}-bar overlap — "
                    f"long overlaps amplify BPM drift; use breakdown masking (≤16 bars)"))

    # Reasoning quality
    reasoning = script.reasoning or ""
    if len(reasoning) < 40:
        issues.append(ValidationIssue("WARNING", "thin_reasoning", "reasoning too short"))
    for keyword, patterns in {
        "bar":     [r"\bbar\b"],
        "bpm":     [r"\bbpm\b"],
        "key":     [r"\bkey\b", r"\b\d{1,2}[AB]\b"],
        "bass":    [r"\bbass\b"],
    }.items():
        if not any(re.search(p, reasoning, re.IGNORECASE) for p in patterns):
            issues.append(ValidationIssue("INFO", f"reasoning_missing_{keyword}",
                f"reasoning doesn't mention '{keyword}'"))

    return issues


# ── Per-pair runner ───────────────────────────────────────────────────────────

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
    log.info("PAIR [bucket=%s]: %r → %r", pair.bucket, getattr(t1, "title", t1.file),
             getattr(t2, "title", t2.file))
    log.info("  T1: %.1f BPM  %s  %d bars", t1.bpm, k1, t1.bar_grid.n_bars)
    log.info("  T2: %.1f BPM  %s  %d bars", t2.bpm, k2, t2.bar_grid.n_bars)
    log.info("  Camelot dist=%d  BPM delta=%.1f  bucket=%s",
             pair.camelot_dist, pair.bpm_delta, pair.bucket)

    t_start = time.monotonic()
    window = None
    script = None
    norm_script = None
    issues: list[ValidationIssue] = []
    error: Optional[str] = None

    try:
        log.info("--- Phase 1: select_transition_window ---")
        window = select_transition_window(t1, t2, MODEL)
        log.info("Window: t1_exit=%d  t2_enter=%d  overlap=%d  style=%s",
                 window["t1_exit_bar"], window["t2_enter_bar"],
                 window["window_bars"], window["style"])

        log.info("--- Phase 2: plan_transition ---")
        from analyze import analyze_transition_zone as _zone
        t1_zone = _zone(t1.file, t1.bpm, t1.first_downbeat_s,
                        max(0, window["t1_exit_bar"] - 8), 24)
        t2_zone = _zone(t2.file, t2.bpm, t2.first_downbeat_s,
                        max(0, window["t2_enter_bar"]), 24)

        script = plan_transition(t1, t2, t1_zone, t2_zone, window, MODEL)
        log.info("Script: %d actions", len(script.actions))
        log.info("Reasoning: %s", script.reasoning)
        log.info("Actions (pre-normalize):")
        for a in script.actions:
            log.info("  %s", json.dumps(a.__dict__, default=str, separators=(",", ":")))

        log.info("--- Normalizer ---")
        norm_script = normalize(script)
        added = [a for a in norm_script.actions if a not in script.actions]
        if added:
            log.info("Normalizer injected %d:", len(added))
            for a in added:
                log.info("  + %s", json.dumps(a.__dict__, default=str, separators=(",", ":")))
        else:
            log.info("Normalizer: clean")

        log.info("--- Validation ---")
        issues = validate_script(norm_script, pair)
        if not issues:
            log.info("PASS — no issues")
        else:
            for iss in issues:
                fn = {"ERROR": log.error, "WARNING": log.warning}.get(iss.severity, log.info)
                fn("[%s] %s: %s", iss.severity, iss.rule, iss.detail)

    except Exception as exc:
        error = traceback.format_exc()
        log.error("EXCEPTION: %s\n%s", exc, error)

    duration_s = time.monotonic() - t_start
    log.info("Pair completed in %.1fs", duration_s)
    return PairResult(pair=pair, window=window, script=script, norm_script=norm_script,
                      issues=issues, error=error, duration_s=duration_s)


# ── Summary ───────────────────────────────────────────────────────────────────

def write_summary(results: list[PairResult], out_dir: Path) -> None:
    lines = [
        "=" * 72,
        f"STRESS SIMULATION SUMMARY  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Model: {MODEL}  Pairs: {len(results)}",
        "Buckets: A=dist2  B=dist≥3  C=large-BPM-gap  D=large-BPM+cross-range",
        "=" * 72, "",
    ]

    bucket_stats: dict[str, dict] = {b: {"total": 0, "clean": 0, "errors": 0, "warns": 0}
                                      for b in "ABCD"}
    total_injected = 0

    for i, r in enumerate(results, 1):
        t1, t2 = r.pair.t1, r.pair.t2
        k1 = getattr(t1.key, "camelot", "?")
        k2 = getattr(t2.key, "camelot", "?")
        b = r.pair.bucket
        bucket_stats[b]["total"] += 1

        errors   = sum(1 for iss in r.issues if iss.severity == "ERROR")
        warnings = sum(1 for iss in r.issues if iss.severity == "WARNING")

        if r.error:
            status = "CRASH"
        elif errors:
            status = f"{errors}E {warnings}W"
            bucket_stats[b]["errors"] += 1
        elif warnings:
            status = f"0E {warnings}W"
            bucket_stats[b]["warns"] += 1
        else:
            status = "CLEAN"
            bucket_stats[b]["clean"] += 1

        lines.append(
            f"[{i:2d}][{b}] {status:8s}  dist={r.pair.camelot_dist}  "
            f"ΔBPM={r.pair.bpm_delta:.1f}  {k1}→{k2}  "
            f"{Path(t1.file).stem[:25]} → {Path(t2.file).stem[:25]}"
        )

        if r.window:
            lines.append(
                f"         Window: exit=b{r.window['t1_exit_bar']}  "
                f"overlap={r.window['window_bars']}bars  style={r.window['style']}"
            )

        if r.script:
            lines.append(f"         Reasoning: {r.script.reasoning[:110]}")

        if r.norm_script and r.script:
            injected = [a for a in r.norm_script.actions if a not in r.script.actions]
            if injected:
                total_injected += len(injected)
                lines.append(f"         Injected: {[a.type+'('+a.track+')' for a in injected]}")

        for iss in r.issues:
            if iss.severity in ("ERROR", "WARNING"):
                lines.append(f"         [{iss.severity}] {iss.rule}: {iss.detail}")

        if r.error:
            lines.append(f"         CRASH: {r.error.splitlines()[-1]}")
        lines.append(f"         Duration: {r.duration_s:.1f}s")
        lines.append("")

    lines += ["=" * 72, "BUCKET SUMMARY", ""]
    bucket_labels = {
        "A": "dist=2  (borderline — mid suppression expected)",
        "B": "dist≥3  (incompatible — cut or ≤8-bar blend expected)",
        "C": "ΔBPM>4  (large gap — breakdown masking expected)",
        "D": "ΔBPM>4 + cross-range  (hardest case)",
    }
    for b, label in bucket_labels.items():
        s = bucket_stats[b]
        if s["total"] == 0:
            lines.append(f"  [{b}] {label}: no pairs found in library")
        else:
            lines.append(f"  [{b}] {label}:")
            lines.append(f"       {s['clean']}/{s['total']} clean  "
                         f"{s['errors']} errors  {s['warns']} warnings")

    lines += [
        "",
        f"Total normalizer injections: {total_injected}",
        "",
        "ISSUE BREAKDOWN:",
    ]
    rule_counts: dict[str, int] = {}
    for r in results:
        for iss in r.issues:
            rule_counts[iss.rule] = rule_counts.get(iss.rule, 0) + 1
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rule}: {count}")

    summary_path = out_dir / "summary.txt"
    summary_path.write_text("\n".join(lines) + "\n")
    print(f"\n{'='*72}")
    print("\n".join(lines))
    print(f"\nFull logs: {out_dir}/")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S"))
    root_log = logging.getLogger("stress")
    root_log.setLevel(logging.INFO)
    root_log.addHandler(ch)

    root_log.info("Loading library (BPM %d–%d)...", BPM_LOW, BPM_HIGH)
    analyses = _load_analyses()
    root_log.info("Loaded %d tracks", len(analyses))

    root_log.info("Building stress pairs...")
    pairs = _build_stress_pairs(analyses)
    root_log.info("Selected %d pairs", len(pairs))

    bucket_counts: dict[str, int] = {}
    for p in pairs:
        bucket_counts[p.bucket] = bucket_counts.get(p.bucket, 0) + 1
        root_log.info(
            "  [%s] dist=%d  ΔBPM=%.1f  %s→%s  %s → %s",
            p.bucket, p.camelot_dist, p.bpm_delta,
            getattr(p.t1.key, "camelot", "?"),
            getattr(p.t2.key, "camelot", "?"),
            Path(p.t1.file).stem[:28],
            Path(p.t2.file).stem[:28],
        )
    for b, c in sorted(bucket_counts.items()):
        root_log.info("  Bucket %s: %d pairs", b, c)

    results: list[PairResult] = []
    for i, pair in enumerate(pairs, 1):
        t1_name = Path(pair.t1.file).stem[:20]
        t2_name = Path(pair.t2.file).stem[:20]
        log_name = f"{i:02d}_{pair.bucket}_{t1_name}__{t2_name}".replace(" ", "_").replace("/", "-")
        log_path = OUT_DIR / f"{log_name}.log"

        root_log.info("\n[%d/%d] [%s] %s → %s (dist=%d ΔBPM=%.1f)",
                      i, len(pairs), pair.bucket, t1_name, t2_name,
                      pair.camelot_dist, pair.bpm_delta)

        pair_log, fh = _build_pair_logger(f"stress.pair{i}", log_path)
        _configure_global_debug(fh)

        result = run_pair(pair, pair_log)
        results.append(result)

        pair_log.removeHandler(fh)
        for name in ("mix_director", "normalizer"):
            logging.getLogger(name).removeHandler(fh)
        fh.close()

        errors   = sum(1 for x in result.issues if x.severity == "ERROR")
        warnings = sum(1 for x in result.issues if x.severity == "WARNING")
        if result.error:
            status = "CRASH"
        elif errors or warnings:
            status = f"{errors}E {warnings}W"
        else:
            status = "CLEAN"
        root_log.info("  → %s  (%.1fs)", status, result.duration_s)

    write_summary(results, OUT_DIR)


if __name__ == "__main__":
    main()
