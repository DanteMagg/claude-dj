#!/usr/bin/env python3
"""
Pull real DJ transition examples from djmix-dataset for dj_skill.md Section 8.

Pipeline:
  1. Parse djmix-dataset.json, filter for tech house / techno / trance / D&B mixes
  2. Find consecutive track pairs where both have YouTube IDs + timestamps
  3. Download individual track audio via yt-dlp (NOT the blended mix)
  4. Analyze each track (BPM, key, sections, cue points) via analyze.py
  5. Plan a rule-based transition from the cue points
  6. Output formatted Section 8 examples

Usage:
  cd /Users/DantesFolder/Claude\ DJ
  python scripts/extract_transitions.py

Output: djmix-examples/section8_draft.md
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_DJ    = PROJECT_ROOT / "claude-dj"
DATASET_JSON = Path("/tmp/djmix-dataset.json")
DOWNLOAD_DIR = PROJECT_ROOT / "djmix-examples" / "tracks"
OUT_FILE     = PROJECT_ROOT / "djmix-examples" / "section8_draft.md"

sys.path.insert(0, str(CLAUDE_DJ))

# ── Dataset filtering ──────────────────────────────────────────────────────────
# Focus on genres where DJs mix harmonically — drop techno/D&B (rhythm-first genres)
TARGET_TAGS = {
    "Category:Tech House",
    "Category:Deep Tech House",
    "Category:House",
    "Category:Deep House",
    "Category:Progressive House",
    "Category:Trance",
}

# Prefer mixes from well-curated series
PREFERRED_TAGS = {
    "Category:Boiler Room",
    "Category:Resident Advisor Podcast",
    "Category:Essential Mix",
    "Category:Fabric",
    "Category:Mixmag",
}

GENRE_MAP = {
    "Category:Tech House":        "tech house",
    "Category:Deep Tech House":   "tech house",
    "Category:House":             "house",
    "Category:Deep House":        "deep house",
    "Category:Progressive House": "progressive house",
    "Category:Trance":            "trance",
}

# ── Timestamp / title parsing ──────────────────────────────────────────────────
TS_RE = re.compile(r"\[(\d+):(\d{2})(?::(\d{2}))?\]")

def parse_timestamp(title: str) -> Optional[int]:
    m = TS_RE.search(title)
    if not m:
        return None
    a, b, c = m.groups()
    if c:
        return int(a) * 3600 + int(b) * 60 + int(c)
    return int(a) * 60 + int(b)

def parse_track_info(title: str) -> tuple[str, str]:
    clean = TS_RE.sub("", title).strip()
    clean = re.sub(r"\s*\[[^\]]*\]\s*$", "", clean).strip()
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", clean).strip()
    if " - " in clean:
        parts = clean.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return "Unknown", clean

# ── Candidate selection ────────────────────────────────────────────────────────
def find_candidates(data: list, target: int = 60) -> list[dict]:
    candidates: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for mix in data:
        tags = {t["key"] for t in mix.get("tags", [])}
        genre_tags = tags & TARGET_TAGS
        if not genre_tags:
            continue

        genre = GENRE_MAP.get(next(iter(genre_tags)), "unknown")
        preferred = bool(tags & PREFERRED_TAGS)
        tracklist = mix.get("tracklist", [])

        for i in range(len(tracklist) - 1):
            t1, t2 = tracklist[i], tracklist[i + 1]
            if not t1["id"] or not t2["id"]:
                continue
            pair = (t1["id"], t2["id"])
            if pair in seen_pairs:
                continue

            ts1 = parse_timestamp(t1["title"])
            ts2 = parse_timestamp(t2["title"])
            if ts1 is None or ts2 is None:
                continue
            gap = ts2 - ts1
            # 2–15 min per track slot
            if gap < 120 or gap > 900:
                continue

            a1, ti1 = parse_track_info(t1["title"])
            a2, ti2 = parse_track_info(t2["title"])
            seen_pairs.add(pair)

            candidates.append({
                "mix_title":  mix["title"][:80],
                "genre":      genre,
                "preferred":  preferred,
                "t1_yt":      t1["id"],
                "t1_artist":  a1,
                "t1_title":   ti1,
                "t1_start_s": ts1,
                "t2_yt":      t2["id"],
                "t2_artist":  a2,
                "t2_title":   ti2,
                "t2_start_s": ts2,
                "gap_s":      gap,
            })

    # Sort: preferred first, then closer to 6 min (balanced transition)
    candidates.sort(key=lambda c: (not c["preferred"], abs(c["gap_s"] - 360)))

    # No genre cap — we want adjacent-key pairs regardless of genre balance
    return candidates[:target]

# ── yt-dlp download ────────────────────────────────────────────────────────────
def download_track(yt_id: str) -> Optional[Path]:
    dest = DOWNLOAD_DIR / f"{yt_id}.mp3"
    if dest.exists():
        return dest
    print(f"  [yt-dlp] downloading {yt_id} ...", flush=True)
    result = subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "-o", str(DOWNLOAD_DIR / f"{yt_id}.%(ext)s"),
            f"https://www.youtube.com/watch?v={yt_id}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  [yt-dlp] FAILED {yt_id}: {result.stderr[-200:]}")
        return None
    return dest if dest.exists() else None

# ── Analysis ───────────────────────────────────────────────────────────────────
def analyze(path: Path, track_id: str):
    from analyze import analyze_track
    return analyze_track(str(path), track_id, no_stems=True)

# ── Transition planner (rule-based, no API calls) ─────────────────────────────
def plan_transition(t1, t2) -> dict:
    """
    Rule-based transition from cue points. Returns action list + metadata.
    Follows the same logic documented in dj_skill.md section 3 and 6.
    """
    cue1 = {c.name: c.bar for c in t1.cue_points}
    cue2 = {c.name: c.bar for c in t2.cue_points}

    t1_mix_in  = cue1.get("mix_in", 0)
    t1_mix_out = cue1.get("mix_out") or cue1.get("breakdown_start") or max(0, t1.bar_grid.n_bars - 32)
    t2_mix_in  = cue2.get("mix_in", 0)

    # Snap to phrase boundary (multiple of 8)
    def snap(b: int) -> int:
        return (b // 8) * 8

    # Global bar where T2 fade_in starts = bars T1 plays before transition
    global_transition_bar = snap(t1_mix_out - t1_mix_in)
    global_transition_bar = max(16, global_transition_bar)  # minimum 16 bars of T1

    # Detect section type at T1's exit for overlap duration
    exit_sections = [s for s in t1.sections if s.start_bar <= t1_mix_out <= s.end_bar]
    exit_label = exit_sections[0].label if exit_sections else "groove"

    # Overlap: 32 bars for breakdown/outro exits, 16 for groove exits
    if exit_label in ("outro", "breakdown"):
        overlap_bars = 32
    else:
        overlap_bars = 16

    # Check harmonic distance (Camelot)
    def camelot_distance(k1: str, k2: str) -> int:
        if k1 == k2:
            return 0
        # same number, different letter (A↔B) = 1
        n1, l1 = k1[:-1], k1[-1]
        n2, l2 = k2[:-1], k2[-1]
        if n1 == n2:
            return 1
        # numeric distance on wheel (12 positions, wrap at 12)
        diff = abs(int(n1) - int(n2))
        return min(diff, 12 - diff)

    camelot_dist = camelot_distance(t1.key.camelot, t2.key.camelot)
    key_note = ""
    if camelot_dist == 0:
        key_note = "same key"
    elif camelot_dist == 1:
        key_note = f"+1 move ({t1.key.camelot}→{t2.key.camelot})"
        if exit_label not in ("outro", "breakdown"):
            overlap_bars = 16  # keep short if not in a safe section
    else:
        key_note = f"{camelot_dist}-step clash ({t1.key.camelot}→{t2.key.camelot}) — reduced overlap"
        overlap_bars = 8

    # BPM gap
    bpm_gap = abs(t1.bpm - t2.bpm)
    bpm_note = ""
    if bpm_gap > 5:
        bpm_note = f" | {bpm_gap:.1f} BPM gap"

    # Bass swap at 50% of overlap, snapped to 8-bar boundary
    bass_swap_bar = snap(global_transition_bar + overlap_bars // 2)

    # Stems: suppress bass on T2 until swap, reduce other stems for key clashes
    if camelot_dist >= 2:
        t2_stems = {"drums": 0.8, "bass": 0.0, "vocals": 0.0, "other": 0.0}
    else:
        t2_stems = {"drums": 0.8, "bass": 0.0, "vocals": 0.0, "other": 0.6}

    actions = [
        {"type": "play",     "track": "T1", "at_bar": 0,
         "from_bar": t1_mix_in},
        {"type": "fade_in",  "track": "T2",
         "start_bar": global_transition_bar,
         "duration_bars": overlap_bars,
         "from_bar": t2_mix_in,
         "stems": t2_stems},
        {"type": "bass_swap","track": "T1",
         "at_bar": bass_swap_bar,
         "incoming_track": "T2"},
        {"type": "play",     "track": "T2",
         "at_bar": global_transition_bar + overlap_bars,
         "from_bar": t2_mix_in + overlap_bars},
        {"type": "fade_out", "track": "T1",
         "start_bar": global_transition_bar,
         "duration_bars": overlap_bars},
    ]

    return {
        "actions": actions,
        "global_transition_bar": global_transition_bar,
        "overlap_bars": overlap_bars,
        "bass_swap_bar": bass_swap_bar,
        "exit_label": exit_label,
        "key_note": key_note,
        "bpm_note": bpm_note,
        "camelot_dist": camelot_dist,
    }

# ── Section 8 example formatter ────────────────────────────────────────────────
def format_example(idx: int, candidate: dict, t1, t2, plan: dict) -> str:
    bpm_range = f"{min(t1.bpm, t2.bpm):.0f}–{max(t1.bpm, t2.bpm):.0f}" \
                if abs(t1.bpm - t2.bpm) > 0.5 else f"{t1.bpm:.0f}"
    actions_json = json.dumps(plan["actions"], indent=2)

    # Build scenario description
    scenario = (
        f"{t1.key.camelot} → {t2.key.camelot} | {plan['key_note']} | "
        f"{bpm_range} BPM{plan['bpm_note']} | "
        f"T1 exits via {plan['exit_label']} | "
        f"{plan['overlap_bars']}-bar overlap"
    )

    mix_context = f"Source: {candidate['mix_title'][:70]}"

    return f"""
### 8.{idx} {candidate['genre'].title()} blend — {plan['key_note']} ({plan['overlap_bars']}-bar {plan['exit_label']} exit)

**Tracks:** {t1.artist} — "{t1.title}" [T1] → {t2.artist} — "{t2.title}" [T2]
**T1:** {t1.bpm:.1f} BPM · {t1.key.camelot} ({t1.key.standard})
**T2:** {t2.bpm:.1f} BPM · {t2.key.camelot} ({t2.key.standard})
**Scenario:** {scenario}
**Source mix:** {mix_context}

```json
{actions_json}
```

T1 plays from bar {plan['actions'][0]['from_bar']} (mix_in). Transition starts at global bar {plan['global_transition_bar']} (T1's {plan['exit_label']} section). T2 fades in over {plan['overlap_bars']} bars with bass held at 0. Bass swap at bar {plan['bass_swap_bar']}. T2 full groove at bar {plan['global_transition_bar'] + plan['overlap_bars']}.

---
"""

# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading {DATASET_JSON} ...")
    data = json.load(open(DATASET_JSON))
    print(f"  {len(data)} mixes total")

    print("Selecting candidates ...")
    candidates = find_candidates(data, target=200)
    print(f"  {len(candidates)} candidates selected")
    for i, c in enumerate(candidates):
        print(f"  {i+1:2d}. [{c['genre']}] {c['t1_artist']} → {c['t2_artist']} "
              f"(gap {c['gap_s']//60:.0f}m{c['gap_s']%60:.0f}s)")

    examples: list[str] = []
    example_idx = 1

    for cand in candidates:
        print(f"\n[{example_idx}] {cand['t1_artist']} — {cand['t1_title'][:40]}")
        print(f"  → {cand['t2_artist']} — {cand['t2_title'][:40]}")

        # Download
        p1 = download_track(cand["t1_yt"])
        p2 = download_track(cand["t2_yt"])
        if not p1 or not p2:
            print("  SKIP: download failed")
            continue

        # Analyze
        print("  [analyze] T1 ...")
        try:
            t1 = analyze(p1, "T1")
        except Exception as e:
            print(f"  SKIP: T1 analysis failed: {e}")
            continue

        print("  [analyze] T2 ...")
        try:
            t2 = analyze(p2, "T2")
        except Exception as e:
            print(f"  SKIP: T2 analysis failed: {e}")
            continue

        # Patch titles/artists from dataset (more reliable than filename parsing)
        t1.artist = cand["t1_artist"]
        t1.title  = cand["t1_title"]
        t2.artist = cand["t2_artist"]
        t2.title  = cand["t2_title"]

        print(f"  T1: {t1.bpm:.1f} BPM · {t1.key.camelot} · {t1.bar_grid.n_bars} bars")
        print(f"  T2: {t2.bpm:.1f} BPM · {t2.key.camelot} · {t2.bar_grid.n_bars} bars")

        # Plan transition
        plan = plan_transition(t1, t2)
        print(f"  Plan: {plan['key_note']} | {plan['overlap_bars']}-bar {plan['exit_label']} exit")

        # Only keep adjacent-key pairs (same or ±1 Camelot step)
        if plan["camelot_dist"] > 1:
            print(f"  SKIP: Camelot dist {plan['camelot_dist']} — not adjacent key")
            continue

        examples.append(format_example(example_idx, cand, t1, t2, plan))
        example_idx += 1

    # Write output
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Section 8 Draft Examples — Real DJ Transitions\n\n"
        "Generated from djmix-dataset (mir-aidj/djmix-dataset). "
        "Track pairs validated by professional DJs in real mixes. "
        "BPM and key from librosa analysis of individual track audio. "
        "Bar numbers are illustrative — transition structure derived from cue points.\n\n"
        "---\n"
    )
    OUT_FILE.write_text(header + "\n".join(examples))
    print(f"\nDone. {len(examples)} examples written to {OUT_FILE}")


if __name__ == "__main__":
    main()
