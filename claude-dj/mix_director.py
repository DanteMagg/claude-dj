from __future__ import annotations

import json
import logging
import math
import textwrap
import time
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic

from schema import MixAction, MixScript, MixTrackRef, TrackAnalysis

_SKILL_PATH    = Path(__file__).parent / "dj_skill.md"
_EXAMPLES_DIR  = Path(__file__).parent / "examples_bank"
_CONCEPT_DIR   = Path(__file__).parent / "concept_bank"

logger = logging.getLogger("mix_director")


def load_concept(slug: str) -> dict | None:
    """Load a concept from concept_bank/<slug>.json. Returns None if not found."""
    if not slug:
        return None
    path = _CONCEPT_DIR / f"{slug}.json"
    if not path.exists():
        logger.debug("load_concept: no concept file for slug %r", slug)
        return None
    data = json.loads(path.read_text())
    logger.debug("load_concept: loaded %r (%s)", slug, data.get("display_name", "?"))
    return data


def _hr(char: str = "─", width: int = 72) -> str:
    return char * width


def _truncate(s: str, n: int = 600) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n… [{len(s)-n} chars omitted]"

# ---------------------------------------------------------------------------
# Examples retrieval (deterministic RAG)
# ---------------------------------------------------------------------------

def _camelot_distance(a: str, b: str) -> int:
    """Minimum step distance in Camelot wheel (0–6). Same key = 0."""
    if a == b:
        return 0
    try:
        def parse(k: str):
            n = int(k[:-1])
            t = k[-1].upper()
            return n, t
        an, at = parse(a)
        bn, bt = parse(b)
        if at == bt:
            diff = min(abs(an - bn), 12 - abs(an - bn))
            return diff
        # A↔B on same number = relative major/minor = distance 1
        if an == bn:
            return 1
        # Cross A/B diagonal moves: conservative fallback
        diff = min(abs(an - bn), 12 - abs(an - bn))
        return diff + 1
    except Exception:
        return 6


def _load_all_examples() -> list[dict]:
    if not _EXAMPLES_DIR.exists():
        return []
    out = []
    for p in sorted(_EXAMPLES_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            pass
    return out


def _score_example(
    ex: dict,
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    window: dict,
    concept: dict | None = None,
) -> float:
    """
    Lower = more similar. Weighted sum:
      - Camelot key distance (both t1 and t2):  0.4 each
      - BPM delta similarity:                    0.3
      - Genre match:                             0.2
      - Exit section match:                      0.1
    """
    m = ex["meta"]
    score = 0.0

    # Key compatibility — key is a KeyInfo object with .camelot, or occasionally a plain str
    def _camelot(k) -> str:
        if k is None:
            return ""
        if hasattr(k, "camelot"):
            return k.camelot or ""
        return str(k).split("_")[0]

    t1_key = _camelot(t1.key)
    t2_key = _camelot(t2.key)
    score += _camelot_distance(t1_key, m.get("t1_camelot", "")) * 0.4
    score += _camelot_distance(t2_key, m.get("t2_camelot", "")) * 0.4

    # BPM delta similarity
    actual_bpm_delta = abs(t1.bpm - t2.bpm)
    ex_bpm_delta     = m.get("bpm_delta", 0.0)
    score += abs(actual_bpm_delta - ex_bpm_delta) * 0.05  # 0.05 per BPM difference

    # Genre: infer from BPM range
    avg_bpm = (t1.bpm + t2.bpm) / 2
    ex_genre = m.get("genre", "")
    if avg_bpm < 105 and "deep" in ex_genre:
        score -= 0.3
    elif 115 <= avg_bpm < 130 and ex_genre in ("house", "deep_house"):
        score -= 0.2
    elif avg_bpm >= 130 and "tech" in ex_genre:
        score -= 0.2

    # Technique / style matching
    window_style = window.get("style", "blend")
    ex_technique = m.get("technique", "blend")
    ex_exit = m.get("exit_section", "groove")

    # Reward technique match
    if window_style == "drop_swap" and ex_technique == "drop_swap":
        score -= 0.5
    elif window_style == "cut" and ex_technique == "cut":
        score -= 0.5
    elif window_style == "blend" and ex_technique in ("blend", "loop_blend"):
        score -= 0.2

    # Camelot distance >=3 → cut examples become more relevant
    actual_camelot_dist = _camelot_distance(t1_key, t2_key)
    if actual_camelot_dist >= 3 and ex_technique == "cut":
        score -= 0.4
    if actual_camelot_dist <= 1 and ex_technique == "cut":
        score += 0.5  # penalize cut examples for compatible keys

    # Loop-blend scenarios — heavily boost loop examples so they surface despite Camelot distance
    t1_bar_grid = getattr(t1, "bar_grid", None)
    t1_bars     = getattr(t1_bar_grid, "n_bars", None)
    t1_exit     = window.get("t1_exit_bar", 64)
    t1_short_runway = t1_bars is not None and (t1_bars - t1_exit) < 20
    # Detect peak-hold scenario: T1 exits hot, T2 has clean percussion intro
    t2_enter_bar = window.get("t2_enter_bar", 0)
    t2_zone_hint = window.get("t2_zone", [])  # populated when available
    # Approximate peak-hold from energy metadata: T2 energy present but T1 is high energy
    t1_energy = getattr(t1, "energy_overall", 5)
    t2_energy = getattr(t2, "energy_overall", 5)
    t1_high_exit = t1_energy >= 5  # T1 exits hot
    if ex_technique == "loop_blend":
        if t1_short_runway:
            score -= 1.0  # strong boost — loop is the right tool for short runway
        elif t1_high_exit and window_style == "blend":
            score -= 0.7  # peak-hold scenario: loop adds character to a hot-exit blend
        else:
            score -= 0.2  # general mild boost so loops get occasional exposure

    # Exit section match
    if window_style == "blend" and ex_exit in ("groove", "intro"):
        score -= 0.1
    elif window_style == "drop_swap" and ex_exit == "drop":
        score -= 0.1

    if concept and ex.get("id") in concept.get("example_ids", []):
        score -= 0.8

    return score


def retrieve_examples(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    window: dict,
    k: int = 2,
    concept: dict | None = None,
) -> list[dict]:
    """Return top-k most relevant examples for this transition."""
    all_ex = _load_all_examples()
    if not all_ex:
        logger.debug("RAG: examples_bank empty — no retrieved examples")
        return []
    scored_pairs = sorted(
        [(e, _score_example(e, t1, t2, window, concept=concept)) for e in all_ex],
        key=lambda x: x[1],
    )
    logger.debug(
        "RAG scores (%d examples) for %s→%s:\n%s",
        len(all_ex),
        getattr(t1.key, "camelot", "?"),
        getattr(t2.key, "camelot", "?"),
        "\n".join(
            f"  score={sc:+.3f}  {e['meta'].get('t1_artist','?')!r}→"
            f"{e['meta'].get('t2_artist','?')!r}  "
            f"({e['meta'].get('t1_camelot','?')}→{e['meta'].get('t2_camelot','?')}  "
            f"{e['meta'].get('technique','?')} exit={e['meta'].get('exit_section','?')})"
            for e, sc in scored_pairs[:8]
        ),
    )
    top = [e for e, _ in scored_pairs[:k]]
    if top:
        logger.debug(
            "RAG selected top-%d:\n%s",
            k,
            "\n".join(
                f"  [{i+1}] {e['meta'].get('t1_artist','?')} → "
                f"{e['meta'].get('t2_artist','?')}  "
                f"{e['meta'].get('t1_camelot','?')}→{e['meta'].get('t2_camelot','?')}"
                for i, e in enumerate(top)
            ),
        )
    return top


def _format_examples_block(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = ["SIMILAR TRANSITIONS FROM PROFESSIONAL DJ MIXES:\n"]
    for ex in examples:
        m = ex["meta"]
        lines.append(
            f"EXAMPLE: {m['t1_artist']} \"{m['t1_title']}\" → {m['t2_artist']} \"{m['t2_title']}\""
        )
        lines.append(
            f"  {m['t1_camelot']}→{m['t2_camelot']} | {m['t1_bpm']}→{m['t2_bpm']} BPM "
            f"(Δ{m['bpm_delta']:.1f}) | {m['genre']} | {m['exit_section']} exit | "
            f"{m['overlap_bars']}-bar overlap | source: {m['source']}"
        )
        arc = ex.get("transition_arc", "")
        if arc:
            lines.append(f"  MUSICAL ARC: {arc}")
        lines.append("  ANNOTATED ACTIONS:")
        for ann in ex.get("annotated_actions", []):
            a = ann["action"]
            action_json = json.dumps(a, separators=(",", ":"))
            lines.append(f"    {action_json}")
            if "t1_state" in ann:
                lines.append(f"      T1 at this moment: {ann['t1_state']}")
            if "t2_state" in ann:
                lines.append(f"      T2 at this moment: {ann['t2_state']}")
            lines.append(f"      WHY: {ann['why']}")
        lines.append("")
    lines.append(
        "IMPORTANT: Do NOT copy these bar numbers — they are from different tracks. "
        "Study the MUSICAL ARC and WHY annotations to understand the decision logic, "
        "then apply that logic to the zone data for the actual tracks below.\n"
    )
    return "\n".join(lines) + "\n"

_TASK_PROMPT = """
---

## YOUR TASK

You are the Claude DJ brain. Output a professional mix script as JSON from the structured track analysis below. Follow the skill document and operational checklist in section 6 for every transition.

---

### FADE_OUT IS MANDATORY FOR EVERY NON-FINAL TRACK

Every track except the very last MUST have a `fade_out`. Schedule it at the mix_out cue or BREAKDOWN. The normalizer will inject one as a safety net but it will be placed wrong.

### FADE_IN IS MANDATORY FOR EVERY BLEND TRANSITION

**If Camelot dist ≤ 2: ALWAYS use `fade_in`, even when both tracks have vocals.**
Dual vocals do NOT justify CUT on a compatible key pair. Use `stems: {drums:0.8, bass:0.0, vocals:0.0, other:0.6}` to hold back T2's vocal during the blend — T2 enters as rhythm + texture only. Release T2's vocal after `bass_swap` by omitting the `vocals` key from stems (or using a fresh `play` action). This is exactly what stems are for.

A bare `play(T2)` while T1 is audible = full-volume slam-in. NEVER do this on a blend.

CUT is only correct when **Camelot dist ≥ 3**. On dist ≤ 2, always `fade_in`.

---

### STEMS — T2 enters via stems, not EQ

Use `stems` in `fade_in` to control which parts of T2 come in and at what volume.
T2 enters as rhythm + texture only — no bass, no lead vocal yet.

```
eq(T2, bar=<fade_in.start_bar>, low=0.0)                         // kill T2 bass
fade_in(T2, start_bar=X, duration_bars=N, from_bar=Y,
         stems={"drums": 0.8, "bass": 0.0, "other": 0.6})        // kick+texture only
bass_swap(T1, at_bar=<midpoint multiple of 8>, incoming_track="T2")
eq(T2, bar=<bass_swap.at_bar>, low=1.0)                          // restore T2 bass
play(T2, at_bar=X+N, from_bar=Y+N)                               // T2 full playback
fade_out(T1, start_bar=X, duration_bars=N)
```

**Default stems values:** `{"drums": 0.8, "bass": 0.0, "other": 0.6}`.
Adjust `other` lower (0.3–0.5) for harmonic clash or higher (0.8) for dense texture blend.
Set `vocals: 0.0` explicitly when T2 has a strong vocal and you want it held back until after bass_swap.

### EQ RAMPS — smooth like a real DJ knob

Add `eq_duration_bars` to make any EQ change ramp smoothly instead of snapping.

```
eq(T1, bar=<fade_in.start_bar - 8>, low=1.0, mid=0.5, eq_duration_bars=4)  // mid ramps down over 4 bars
eq(T1, bar=<fade_in.start_bar>, low=0.0, eq_duration_bars=2)                // bass cuts over 2 bars
```

Use `eq_duration_bars: 2–4` for all EQ changes. Never let them snap (no duration = jarring).

### GAIN — duck T1 volume independently

```
gain(T1, at_bar=<8 bars before fade_out>, volume=0.7, duration_bars=8)  // gentle level duck
```

`volume`: 0.0=silence, 1.0=unity. Use for riding levels, not replacing fade_out.

---

### OUTPUT SCHEMA

Output ONLY valid JSON. `reasoning`: 3–5 sentences citing section labels, bar numbers, key move, energy arc, bass swap placement.

```json
{
  "mix_title": "string",
  "reasoning": "string",
  "tracks": [
    {"id": "T1", "path": "string", "bpm": 128.0, "first_downbeat_s": 0.5}
  ],
  "actions": [
    {"type": "play",      "track": "T1", "at_bar": 16, "from_bar": 16},
    {"type": "eq",        "track": "T1", "bar": 72,    "low": 1.0, "mid": 0.5, "eq_duration_bars": 4},
    {"type": "eq",        "track": "T2", "bar": 80,    "low": 0.0},
    {"type": "fade_in",   "track": "T2", "start_bar": 80, "duration_bars": 16, "from_bar": 8, "stems": {"drums": 0.8, "bass": 0.0, "other": 0.6}},
    {"type": "bass_swap", "track": "T1", "at_bar": 88, "incoming_track": "T2"},
    {"type": "eq",        "track": "T2", "bar": 88,    "low": 1.0},
    {"type": "play",      "track": "T2", "at_bar": 96, "from_bar": 24},
    {"type": "fade_out",  "track": "T1", "start_bar": 80, "duration_bars": 16},
    {"type": "loop",      "track": "T1", "start_bar": 64, "loop_bars": 8, "loop_repeats": 2}
  ]
}
```

Bar values are LOCAL to each track's first downbeat. `eq` values: 0.0=kill, 1.0=unity. `bass_swap.at_bar` and `loop.start_bar` must be multiples of 8.
"""


def _load_system_prompt() -> str:
    if _SKILL_PATH.exists():
        skill = _SKILL_PATH.read_text()
    else:
        import sys
        print(
            f"[mix_director] WARNING: {_SKILL_PATH} not found -- "
            "Claude will receive no DJ skill context. Commit dj_skill.md to fix this.",
            file=sys.stderr,
        )
        skill = ""
    return skill + _TASK_PROMPT


def _energy_sparkline(curve_str: str, width: int = 64) -> str:
    """Downsample energy_curve_per_bar to `width` chars, return a sparkline string."""
    if not curve_str:
        return ""
    blocks = " ▁▂▃▄▅▆▇█"
    n = len(curve_str)
    out = []
    for i in range(width):
        idx = int(i * n / width)
        val = int(curve_str[idx]) if idx < n else 0
        out.append(blocks[min(val, 8)])
    return "".join(out)


def _format_track_summary(a: TrackAnalysis, tid: str) -> str:
    """
    Produce a dense human-readable track summary for the prompt.

    Includes: ID, title, BPM, key, duration, sections with semantic labels,
    cue points, and a 64-char energy sparkline.
    """
    total_bars = a.bar_grid.n_bars

    # Section summary -- semantic labels with bar ranges, energy, and active stems
    section_parts = []
    for s in a.sections:
        stems_present = []
        if s.stems.drums.presence >= 5:   stems_present.append("drums")
        if s.stems.bass.presence  >= 5:   stems_present.append("bass")
        if s.stems.vocals.presence >= 5:  stems_present.append("vox")
        if s.stems.other.presence  >= 5:  stems_present.append("other")
        stem_tag = "+".join(stems_present) if stems_present else "sparse"
        section_parts.append(
            f"{s.label.upper()}(b{s.start_bar}-{s.end_bar},e={s.energy},{stem_tag})"
        )
    section_str = " -> ".join(section_parts) if section_parts else "unknown"

    # Cue point summary
    cue_map = {c.name: c.bar for c in a.cue_points}
    cue_parts = []
    for name in ("mix_in", "drop_bar", "breakdown_start", "mix_out"):
        if name in cue_map:
            cue_parts.append(f"{name}=b{cue_map[name]}")
    cue_str = "  ".join(cue_parts)

    # Energy sparkline
    sparkline = _energy_sparkline(a.energy_curve_per_bar)

    lines = [
        f"-- {tid}: \"{a.title}\" by {a.artist} --",
        f"   BPM={a.bpm:.1f}  key={a.key.camelot}({a.key.standard})  "
        f"duration={a.duration_s:.0f}s ({total_bars} bars, ~{a.duration_s/60:.1f} min)",
        f"   energy_overall={a.energy_overall}  loudness={a.loudness_dbfs:.1f} dBFS",
        f"   SECTIONS: {section_str}",
        f"   CUES:     {cue_str}",
        f"   ENERGY (bar 0->{total_bars}): [{sparkline}]",
    ]
    return "\n".join(lines)


def build_prompt(analyses: list[TrackAnalysis], min_minutes: Optional[int] = None) -> str:
    summaries = []
    for i, a in enumerate(analyses):
        tid = f"T{i + 1}"
        summaries.append(_format_track_summary(a, tid))

    # Full JSON for structured data Claude may need precisely
    track_dicts = []
    for i, a in enumerate(analyses):
        d = a.to_dict()
        del d["stems"]
        d["id"]   = f"T{i + 1}"
        d["file"] = d["file"].split("/")[-1]
        # Strip verbose rms_db fields from section stems to save tokens
        for s in d.get("sections", []):
            for stem in s.get("stems", {}).values():
                stem.pop("rms_db", None)
        track_dicts.append(d)

    duration_instruction = ""
    if min_minutes:
        duration_instruction = (
            f"\n\nTARGET SET LENGTH: at least {min_minutes} minutes of continuous audio. "
            "Use as much of each track's body as needed to hit this target. "
            "If the tracks are long enough, extend overlap windows and let tracks play longer before transitioning."
        )

    return (
        f"You are planning a mix of {len(analyses)} tracks.{duration_instruction}\n\n"
        + "\n\n".join(summaries)
        + "\n\n"
        + "FULL TRACK DATA (JSON):\n"
        + json.dumps(track_dicts, indent=2)
        + "\n\nUsing the section labels, cue points, and energy curve above, output the mix script JSON now."
    )


# ── Phase 1: window selection ─────────────────────────────────────────────────

_WINDOW_SYSTEM = (
    "You are a DJ assistant selecting transition windows between tracks. "
    "Output ONLY valid JSON — no prose, no markdown fences."
)

# Minimum bars a track must play past its entry point before it may be mixed out.
MIN_PLAY_BARS = 32


def _phrase_floor(bar: int) -> int:
    return (int(bar) // 8) * 8


def _phrase_ceil(bar: int) -> int:
    return -(-int(bar) // 8) * 8


def clamp_t1_exit_bar(
    raw_exit: int,
    n_bars: int,
    window_bars: int,
    entered_at_bar: int = 0,
) -> int:
    """
    Snap a T1 exit bar to a phrase boundary and hold it inside the legal range.

    Ceiling: leave at least window_bars of T1 audio for the overlap to run in.
    Floor:   T1 must play at least MIN_PLAY_BARS past entered_at_bar — the bar in T1's
             OWN timeline where it entered the mix. Bars before that point never reach
             the speakers, so an exit bar below the floor asks the outgoing deck to fade
             out at a moment it has already played past. Downstream that reads as an
             instant fade_out (live) or, once the offsets are applied, a transition
             placed earlier than the one before it (offline merge).
    The ceiling wins when the two conflict — a short track, or an entry point so late
    that MIN_PLAY_BARS simply does not fit.
    """
    max_exit = max(0, _phrase_floor(n_bars - window_bars))
    min_exit = min(max(0, _phrase_ceil(entered_at_bar + MIN_PLAY_BARS)), max_exit)
    return max(min_exit, min(_phrase_floor(raw_exit), max_exit))


_WINDOW_PROMPT_TEMPLATE = """\
Given these two track summaries, choose the optimal transition window.

{summaries}
{profiles_section}{entry_section}{peek_section}
Output a single JSON object:
{{
  "t1_exit_bar":  <int: bar in T1 where fade_out starts — use its mix_out or breakdown_start cue>,
  "t2_enter_bar": <int: bar in T2 where T2 starts fading in — use its mix_in cue (usually 0)>,
  "window_bars":  <int: overlap length, one of 8 / 16 / 24 / 32>,
  "style":        <"blend" | "cut" | "drop_swap">
}}

Rules:
- t1_exit_bar should be T1's mix_out cue (or breakdown_start for a slower blend).
  If the zone data above shows the suggested exit bar still has high drums/rms, push the
  exit later to a lower-energy bar.
  If T1 is mid-set (see above), t1_exit_bar must be past the bar it entered at — bars
  before that never reach the speakers.
- t2_enter_bar should be T2's mix_in cue (usually 0 — the clean intro start).
- window_bars default = 16. Use 32 for deep/prog styles; 8 for key clashes or tight cuts.
- style = "blend" for standard crossfades, "cut" for instant switches, "drop_swap" for matching drops.
"""


def _format_peek_rows(rows: list[dict], probe_bar: int) -> str:
    """Format a handful of zone rows for Phase 1 context."""
    if not rows:
        return ""
    lines = [f"T1 energy around suggested exit (bar {probe_bar}) — drums/harm/rms/onsets:"]
    for r in rows:
        marker = " ← suggested exit" if r["bar"] == probe_bar else ""
        lines.append(
            f"  b{r['bar']:3d}: d={r['drums']:.2f} h={r['harmonic']:.2f} "
            f"r={r['rms']:.2f} on={r['onsets']}{marker}"
        )
    return "\n".join(lines) + "\n\n"


def _format_profiles_section(t1_profile, t2_profile) -> str:
    """Format mixing profile summaries for Phase 1 window selection prompt."""
    if t1_profile is None and t2_profile is None:
        return ""

    lines: list[str] = []

    if t1_profile is not None:
        vocal_str = (
            "bars " + ", ".join(f"{s}–{e}" for s, e in t1_profile.vocal_bars)
            if t1_profile.vocal_bars else "none"
        )
        best_exit = t1_profile.transition_windows[0] if t1_profile.transition_windows else None
        exit_str = (
            f"bar {best_exit.bar} (quality={best_exit.quality}, {best_exit.character})"
            if best_exit else "unknown"
        )
        notes_preview = t1_profile.dj_notes[:120] + "…" if len(t1_profile.dj_notes) > 120 else t1_profile.dj_notes
        lines += [
            "T1 MIXING PROFILE:",
            f"  intro: {t1_profile.intro_type} | outro: {t1_profile.outro_type}",
            f"  vocals: {vocal_str} — avoid overlapping these bars during transition",
            f"  best exit window: {exit_str}",
            f"  DJ notes: \"{notes_preview}\"",
        ]

    if t2_profile is not None:
        first_voc = min(t2_profile.vocal_bars[0]) if t2_profile.vocal_bars else None
        voc_str = f"first vocal bar {first_voc}" if first_voc is not None else "no vocals detected"
        lines += [
            "",
            "T2 MIXING PROFILE:",
            f"  intro: {t2_profile.intro_type} | outro: {t2_profile.outro_type}",
            f"  {voc_str}",
        ]
        if t2_profile.dj_notes and "[stems unavailable" not in t2_profile.dj_notes:
            notes_preview = t2_profile.dj_notes[:120] + "…" if len(t2_profile.dj_notes) > 120 else t2_profile.dj_notes
            lines.append(f"  DJ notes: \"{notes_preview}\"")

    return "\n".join(lines) + "\n\n"


def select_transition_window(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    model: str,
    concept: dict | None = None,
    t1_entered_at_bar: int = 0,
) -> dict:
    """
    Phase 1: lightweight API call that picks where the transition should happen.
    Runs a quick per-bar energy peek (~8 bars around the default T1 exit) so the
    model can tell whether the suggested cue point is actually low-energy or still
    kicking.  Falls back to cue-point defaults on any error.

    t1_entered_at_bar is the bar in T1's own timeline where T1 entered the mix — 0 for
    the opening track, the incoming deck's from_bar for every transition after that.
    Callers that leave it at 0 get the old behaviour; callers mid-set must pass it, or
    the returned t1_exit_bar can land on audio T1 has already played past.
    """
    logger.debug(
        "%s\nPHASE 1: select_transition_window\n"
        "  T1: %r  bpm=%.1f  key=%s  bars=%d  entered_at_bar=%d\n"
        "  T2: %r  bpm=%.1f  key=%s  bars=%d",
        _hr(),
        getattr(t1, "title", t1.file),
        t1.bpm,
        getattr(t1.key, "camelot", "?"),
        t1.bar_grid.n_bars,
        t1_entered_at_bar,
        getattr(t2, "title", t2.file),
        t2.bpm,
        getattr(t2.key, "camelot", "?"),
        t2.bar_grid.n_bars,
    )

    summaries = (
        _format_track_summary(t1, "T1") + "\n\n" + _format_track_summary(t2, "T2")
    )

    # Sensible defaults derived from cue points (needed before the API call)
    cue_t1 = {c.name: c.bar for c in t1.cue_points}
    cue_t2 = {c.name: c.bar for c in t2.cue_points}
    # The cue points describe the whole track, so a mid-set T1 can point the probe at
    # bars that already played. Clamp before peeking so the zone data the model sees is
    # the zone it can actually still use. 16 = default["window_bars"] below.
    raw_probe_bar = (
        cue_t1.get("mix_out")
        or cue_t1.get("breakdown_start")
        or max(0, t1.bar_grid.n_bars - 32)
    )
    probe_bar = clamp_t1_exit_bar(raw_probe_bar, t1.bar_grid.n_bars, 16, t1_entered_at_bar)

    logger.debug(
        "T1 cues: %s  →  probe_bar=%d%s\nT2 cues: %s",
        cue_t1,
        probe_bar,
        f" (from {raw_probe_bar}, entered_at_bar={t1_entered_at_bar})" if probe_bar != raw_probe_bar else "",
        cue_t2,
    )

    # Quick zone peek: 4 bars lead-in + 8 bars past the suggested exit (~12 bars total)
    # If the mixing profile suggests a better exit window, add a second probe there too.
    peek_section = ""
    peek_rows: list[dict] = []
    t1_profile = getattr(t1, "mixing_profile", None)
    profile_window_bar = (
        t1_profile.transition_windows[0].bar
        if t1_profile and t1_profile.transition_windows
        else None
    )
    try:
        from analyze import analyze_transition_zone as _peek_zone  # local import avoids circular
        peek_rows = _peek_zone(
            t1.file, t1.bpm, t1.first_downbeat_s,
            max(0, probe_bar - 4), 12,
        )
        peek_section = _format_peek_rows(peek_rows, probe_bar)

        # If profile suggests a window far from the cue, show it too
        if profile_window_bar is not None and abs(profile_window_bar - probe_bar) > 8:
            extra_rows = _peek_zone(
                t1.file, t1.bpm, t1.first_downbeat_s,
                max(0, profile_window_bar - 4), 12,
            )
            if extra_rows:
                extra_lines = [f"T1 profile-suggested exit window (bar {profile_window_bar}) — drums/harm/rms/onsets:"]
                for r in extra_rows:
                    marker = " ← profile suggestion" if r["bar"] == profile_window_bar else ""
                    extra_lines.append(
                        f"  b{r['bar']:3d}: d={r['drums']:.2f} h={r['harmonic']:.2f} "
                        f"r={r['rms']:.2f} on={r['onsets']}{marker}"
                    )
                peek_section += "\n".join(extra_lines) + "\n\n"

        logger.debug(
            "Zone peek around T1 exit (probe_bar=%d):\n%s",
            probe_bar,
            "\n".join(
                f"  b{r['bar']:3d}: d={r['drums']:.2f} h={r['harmonic']:.2f} "
                f"r={r['rms']:.2f} onsets={r['onsets']}"
                + (" ← probe" if r["bar"] == probe_bar else "")
                for r in peek_rows
            ),
        )
    except Exception as exc:
        logger.warning("select_window peek failed (%s) — skipping zone hint", exc)
        print(f"[mix_director] select_window peek failed ({exc}) — skipping zone hint")

    # Profile summary injection (Phase 0 data)
    profiles_section = _format_profiles_section(
        getattr(t1, "mixing_profile", None),
        getattr(t2, "mixing_profile", None),
    )

    # Tell the model where T1 came in, so it picks a usable exit instead of leaning on
    # the clamp below to drag an unusable one forward.
    entry_section = ""
    if t1_entered_at_bar > 0:
        entry_section = (
            f"T1 IS MID-SET: it entered the mix at its own bar {t1_entered_at_bar}, so bars "
            f"0–{t1_entered_at_bar} never played. Choose t1_exit_bar at or after bar "
            f"{t1_entered_at_bar + MIN_PLAY_BARS} so T1 gets a real run before it is mixed out.\n\n"
        )

    prompt = _WINDOW_PROMPT_TEMPLATE.format(
        summaries=summaries,
        peek_section=peek_section,
        profiles_section=profiles_section,
        entry_section=entry_section,
    )
    if concept:
        d = concept.get("directives", {})
        avoid = ", ".join(d.get("avoid_technique", []))
        concept_hint = (
            f"ACTIVE CONCEPT: {concept['display_name']}\n"
            f"Prefer: window_bars={d.get('preferred_overlap_bars', 16)}, "
            f"style={d.get('preferred_technique', 'blend')}\n"
            + (f"Avoid: {avoid}\n" if avoid else "")
            + "\n"
        )
        prompt = concept_hint + prompt
    logger.debug("Phase 1 prompt:\n%s", _truncate(prompt, 800))

    default = {
        "t1_exit_bar":  probe_bar,
        "t2_enter_bar": cue_t2.get("mix_in", 0),
        "window_bars":  16,
        "style":        "blend",
    }

    try:
        client = anthropic.Anthropic()
        t0 = time.monotonic()
        response = client.messages.create(
            model=model,
            max_tokens=128,
            system=[{"type": "text", "text": _WINDOW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - t0) * 1000
        usage = response.usage
        logger.debug(
            "Phase 1 API response (%.0fms)  tokens in=%d cache_read=%d out=%d",
            latency_ms,
            usage.input_tokens,
            getattr(usage, "cache_read_input_tokens", 0),
            usage.output_tokens,
        )
        print(
            f"[mix_director] select_window tokens -- "
            f"in:{usage.input_tokens} (cache_read:{getattr(usage, 'cache_read_input_tokens', 0)}) "
            f"out:{usage.output_tokens}"
        )
        raw = response.content[0].text.strip()
        logger.debug("Phase 1 raw response: %s", raw)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        window = json.loads(raw)
        raw_window = dict(window)
        # Validate / clamp
        window.setdefault("t1_exit_bar",  default["t1_exit_bar"])
        window.setdefault("t2_enter_bar", default["t2_enter_bar"])
        window["window_bars"] = max(8, min(32, int(window.get("window_bars", 16))))
        window["style"]       = window.get("style", "blend")
        # Phrase-snap, keep window_bars of T1 audio for the overlap, and keep the exit
        # at least MIN_PLAY_BARS past wherever T1 entered the mix.
        window["t1_exit_bar"] = clamp_t1_exit_bar(
            window["t1_exit_bar"],
            t1.bar_grid.n_bars,
            window["window_bars"],
            t1_entered_at_bar,
        )
        window["t2_enter_bar"] = max(0, int(window["t2_enter_bar"]))
        clamp_notes = []
        if raw_window.get("t1_exit_bar") != window["t1_exit_bar"]:
            clamp_notes.append(
                f"t1_exit_bar {raw_window.get('t1_exit_bar')}→{window['t1_exit_bar']} (clamped)"
            )
        if raw_window.get("window_bars") != window["window_bars"]:
            clamp_notes.append(
                f"window_bars {raw_window.get('window_bars')}→{window['window_bars']} (clamped)"
            )
        logger.debug(
            "Phase 1 window: t1_exit=%d  t2_enter=%d  window=%d  style=%s%s",
            window["t1_exit_bar"],
            window["t2_enter_bar"],
            window["window_bars"],
            window["style"],
            ("  CLAMPS: " + ", ".join(clamp_notes)) if clamp_notes else "",
        )
        return window
    except Exception as exc:
        logger.warning("Phase 1 failed (%s), using cue defaults: %s", exc, default)
        print(f"[mix_director] select_window failed ({exc}), using cue defaults")
        return default


# ── Phase 2: zone table + move planning ───────────────────────────────────────

def _annotate_bar(row: dict, prev: Optional[dict]) -> str:
    """Return a bracketed annotation string for a zone table row."""
    labels = []
    d, h, r = row["drums"], row["harmonic"], row["rms"]

    if r < 0.05:
        labels.append("SILENT")
    elif d < 0.15 and h < 0.15:
        labels.append("SPARSE")
    elif d < 0.25 and r > 0.1:
        labels.append("BREAKDOWN")
    elif d > 0.65 and r > 0.55:
        labels.append("DROP")

    if prev is not None:
        # Rising transitions
        if prev["drums"] < 0.2 and d > 0.55:
            labels.append("KICK-IN")
        if prev["harmonic"] < 0.2 and h > 0.45:
            labels.append("BASS-IN")
        # Falling transitions
        if prev["drums"] > 0.55 and d < 0.2:
            labels.append("KICK-OUT")
        if prev["harmonic"] > 0.45 and h < 0.15:
            labels.append("BASS-OUT")

    return ("  [" + " ".join(labels) + "]") if labels else ""


def _trim_zone(zone: list[dict], max_bars: int) -> list[dict]:
    """Return at most max_bars rows from zone, from the start."""
    return zone[:max_bars]


def _format_situation_summary(
    t1: "TrackAnalysis",
    t2: "TrackAnalysis",
    window: dict,
    t2_zone: list[dict],
) -> str:
    """Produce the compact SITUATION block for the Phase 2 prompt."""
    t1_section = "unknown"
    for s in t1.sections:
        if s.start_bar <= window["t1_exit_bar"] < s.end_bar:
            t1_section = s.label.upper()
            break

    t1_bars_remain = max(0, t1.bar_grid.n_bars - window["t1_exit_bar"])

    t2_profile = getattr(t2, "mixing_profile", None)
    intro_type = t2_profile.intro_type if t2_profile else "unknown"

    first_harm_bar: str = "unknown"
    for r in t2_zone:
        if r.get("harmonic", 0.0) > 0.20:
            first_harm_bar = str(r["bar"])
            break

    camelot_dist = _camelot_distance(
        getattr(t1.key, "camelot", ""),
        getattr(t2.key, "camelot", ""),
    )
    bpm_delta = abs(t1.bpm - t2.bpm)

    return (
        f"SITUATION:\n"
        f"  T1: \"{t1.title}\" by {t1.artist}"
        f" — {t1_section} exit, bar {window['t1_exit_bar']}."
        f" {t1_bars_remain} bars of track remain.\n"
        f"  T2: \"{t2.title}\" by {t2.artist}"
        f" — {intro_type} intro. First harmonic content: bar {first_harm_bar}.\n"
        f"  Key: {t1.key.camelot}→{t2.key.camelot}"
        f" (Camelot dist={camelot_dist}). BPM delta: {bpm_delta:.1f}."
    )


def _format_zone_table(zone: list[dict], track_id: str, label: str) -> str:
    if not zone:
        return f"{track_id} {label}: (no zone data)\n"

    first_bar = zone[0]["bar"]
    last_bar  = zone[-1]["bar"]
    lines = [f"{track_id} {label} (bars {first_bar}–{last_bar}):"]

    prev = None
    for row in zone:
        brightness = "bright" if row["brightness"] > 0.55 else ("mid" if row["brightness"] > 0.30 else "dark ")
        annotation = _annotate_bar(row, prev)
        vocals_val = row.get("vocals", 0.0)
        tags       = row.get("tags", [])
        tag_str    = "  " + " ".join(f"[{t}]" for t in tags) if tags else ""
        lines.append(
            f"  b{row['bar']:3d}: d={row['drums']:.2f} h={row['harmonic']:.2f} "
            f"r={row['rms']:.2f} {brightness} onsets={row['onsets']} "
            f"vox={vocals_val:.2f}{annotation}{tag_str}"
        )
        prev = row

    return "\n".join(lines)


_PLAN_TASK_SUFFIX = ""


def _format_plan_prompt(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
    concept: dict | None = None,
    examples: list[dict] | None = None,
) -> str:
    situation = _format_situation_summary(t1, t2, window, t2_zone)

    t1_rows = _trim_zone(t1_zone, 24)
    t2_rows = _trim_zone(t2_zone, 16)
    t1_table = _format_zone_table(t1_rows, "T1", "exit zone")
    t2_table = _format_zone_table(t2_rows, "T2", "entry zone")

    coord_note = (
        "COORDINATE SYSTEM: All bar values in your output must be LOCAL to each track's "
        "first downbeat (T1 bar 0 = T1's first_downbeat_s, T2 bar 0 = T2's first_downbeat_s). "
        "Do NOT use global mix bar numbers. The zone data bars above are already in track-local space.\n\n"
    )

    loop_safe_bars = [r["bar"] for r in t1_rows if "LOOP_SAFE" in r.get("tags", [])]

    # T2 clean intro: first 8 bars of T2 entry zone have low harmonic (drums-only / sparse)
    t2_enter_bar = window.get("t2_enter_bar", 0)
    t2_first_8   = [r for r in t2_rows if r.get("bar", 0) < t2_enter_bar + 8]
    t2_clean_intro = (
        len(t2_first_8) >= 2
        and all(r.get("harmonic", 1.0) < 0.30 for r in t2_first_8)
    )

    t1_all_high = all(r.get("rms", 1.0) >= 0.5 for r in t1_rows)

    # T1 has short runway: fewer than 20 bars remain after the exit point
    t1_bars_remain = max(0, t1.bar_grid.n_bars - window.get("t1_exit_bar", 0))

    if loop_safe_bars and t1_all_high and t2_clean_intro:
        # Classic peak-hold loop: T1 exits hot, T2 has a percussion-only intro.
        # A straight blend sounds rough here — loop T1 to create rhythmic tension
        # and give T2's percussion intro a stable backdrop to rise against.
        loop_rule = (
            f"3. USE LOOP TECHNIQUE (peak-hold blend — §7, §14.9): "
            f"T1 exit zone is uniformly high-energy AND T2 has a clean percussion intro. "
            f"Pick a LOOP_SAFE bar from {loop_safe_bars[:4]} (avoid vocal bars). "
            "Loop T1 there: loop_bars=8, loop_repeats=1. "
            "Fade T2 in during the loop window (start_bar = loop start, duration_bars=16). "
            "After the loop T1 resumes from loop_start+8 — schedule fade_out there. "
            "A straight blend is the WRONG choice for this scenario."
        )
    elif loop_safe_bars and t1_bars_remain < 20:
        # Short runway: T1 runs out before a 16-bar blend can finish — loop buys the window.
        loop_rule = (
            f"3. USE LOOP TECHNIQUE (extend runway — §7): "
            f"T1 has only {t1_bars_remain} bars remaining — too short for a clean 16-bar blend. "
            f"Loop T1 at a LOOP_SAFE bar ({loop_safe_bars[:4]}) with loop_bars=8, loop_repeats=2 "
            "to create the blend runway. Schedule fade_out at loop_start + loop_bars * loop_repeats."
        )
    elif loop_safe_bars:
        loop_rule = (
            f"3. LOOP OPTION (§7): LOOP_SAFE bars in T1 exit zone: {loop_safe_bars}. "
            "You MAY loop T1 here (loop_bars=8, loop_repeats=1) to add rhythmic tension "
            "before the blend — especially effective when the floor is still responding to T1. "
            "Not required if a straight blend fits the energy arc."
        )
    else:
        loop_rule = "3. No LOOP_SAFE bars in T1 exit zone — use a straight blend."

    if t1_all_high and loop_safe_bars and t2_clean_intro:
        energy_rule = "4. T1 exit zone uniformly high-energy — loop technique handles this (see Rule 3)."
    elif t1_all_high:
        energy_rule = (
            "4. T1 exit zone is uniformly high-energy (all rms ≥ 0.5). "
            "Note this in reasoning — choose the lowest-rms bar as transition anchor."
        )
    else:
        energy_rule = "4. Use the lowest-rms bars in T1 exit zone as the transition runway."

    rules = (
        "RULES:\n"
        "1. Never have two bass-active tracks simultaneously. T2 enters with stems.bass=0.0. "
        "Bass swap happens ≥8 bars after T2 enters, at the lowest-energy bar in zone.\n"
        "2. All EQ moves must include eq_duration_bars (default: 4). No snap cuts.\n"
        f"{loop_rule}\n"
        f"{energy_rule}"
    )

    concept_block = ""
    if concept:
        d = concept.get("directives", {})
        concept_block = (
            f"{'=' * 60}\n"
            f"ACTIVE CONCEPT: {concept['display_name'].upper()}\n\n"
            f"{concept['prompt_injection']}\n\n"
            f"DIRECTIVES SUMMARY: overlap={d.get('preferred_overlap_bars')} bars | "
            f"technique={d.get('preferred_technique')} | "
            f"bass_swap={d.get('bass_swap_placement')}\n"
            f"{'=' * 60}\n\n"
        )

    examples_block = _format_examples_block(examples or [])

    return (
        concept_block
        + coord_note
        + situation + "\n\n"
        + t1_table + "\n\n"
        + t2_table + "\n\n"
        + examples_block
        + rules + "\n\n"
        + "Output the transition actions as JSON."
    )


def plan_transition(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
    model: str,
    concept: dict | None = None,
) -> MixScript:
    """
    Phase 2: full move planning with per-bar zone data injected into the prompt.
    Uses the same output schema as direct_mix.
    """
    camelot_dist = _camelot_distance(
        getattr(t1.key, "camelot", ""),
        getattr(t2.key, "camelot", ""),
    )
    logger.debug(
        "%s\nPHASE 2: plan_transition\n"
        "  Window: t1_exit=%d  t2_enter=%d  overlap=%d  style=%s\n"
        "  Key move: %s→%s (dist=%d)  BPM: %.1f→%.1f (Δ%.1f)\n"
        "  T1 zone: %d bars (%d–%d)\n"
        "  T2 zone: %d bars (%d–%d)",
        _hr(),
        window["t1_exit_bar"], window["t2_enter_bar"], window["window_bars"], window["style"],
        getattr(t1.key, "camelot", "?"), getattr(t2.key, "camelot", "?"), camelot_dist,
        t1.bpm, t2.bpm, abs(t1.bpm - t2.bpm),
        len(t1_zone),
        t1_zone[0]["bar"] if t1_zone else 0,
        t1_zone[-1]["bar"] if t1_zone else 0,
        len(t2_zone),
        t2_zone[0]["bar"] if t2_zone else 0,
        t2_zone[-1]["bar"] if t2_zone else 0,
    )

    if t1_zone:
        logger.debug(
            "T1 exit zone:\n%s",
            "\n".join(
                f"  b{r['bar']:3d}: d={r['drums']:.2f} h={r['harmonic']:.2f} "
                f"r={r['rms']:.2f} onsets={r['onsets']}"
                for r in t1_zone
            ),
        )
    if t2_zone:
        logger.debug(
            "T2 entry zone:\n%s",
            "\n".join(
                f"  b{r['bar']:3d}: d={r['drums']:.2f} h={r['harmonic']:.2f} "
                f"r={r['rms']:.2f} onsets={r['onsets']}"
                for r in t2_zone
            ),
        )

    # Print vocal info from zone data so we can see what the agent was given
    def _vocal_summary(zone, label):
        if not zone:
            return f"{label}: no zone data"
        vocal_bars = [r['bar'] for r in zone if r.get('vocal', 0) > 0.3]
        clean_bars  = [r['bar'] for r in zone if r.get('vocal', 0) <= 0.15]
        return f"{label}: vocal_bars={vocal_bars[:8]} clean_bars={clean_bars[:8]}"
    print(f"[mix_director] {_vocal_summary(t1_zone, 'T1')}")
    print(f"[mix_director] {_vocal_summary(t2_zone, 'T2')}")

    client = anthropic.Anthropic()
    system_text = _load_system_prompt() + _PLAN_TASK_SUFFIX
    examples = retrieve_examples(t1, t2, window, k=2, concept=concept)
    prompt = _format_plan_prompt(t1, t2, t1_zone, t2_zone, window, concept=concept, examples=examples)
    logger.debug("Phase 2 prompt (head/tail):\n%s", _truncate(prompt, 1200))

    t0 = time.monotonic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (time.monotonic() - t0) * 1000

    usage = response.usage
    logger.debug(
        "Phase 2 API response (%.0fms)  tokens in=%d cache_read=%d cache_write=%d out=%d  stop=%s",
        latency_ms,
        usage.input_tokens,
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
        usage.output_tokens,
        response.stop_reason,
    )
    print(
        f"[mix_director] plan_transition tokens -- "
        f"in:{usage.input_tokens} (cache_read:{getattr(usage, 'cache_read_input_tokens', 0)} "
        f"cache_write:{getattr(usage, 'cache_creation_input_tokens', 0)}) "
        f"out:{usage.output_tokens}"
    )

    raw = response.content[0].text.strip()
    logger.debug("Phase 2 raw response:\n%s", _truncate(raw, 2000))
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    if response.stop_reason == "max_tokens":
        logger.warning("Phase 2 response truncated (max_tokens) — continuing")
        print("[mix_director] plan_transition truncated -- continuing")
        followup = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=[
                {"role": "user",      "content": prompt},
                {"role": "assistant", "content": response.content[0].text},
                {"role": "user",      "content": "Your response was cut off. Continue and complete the JSON exactly where you left off."},
            ],
        )
        raw = (response.content[0].text + followup.content[0].text).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(raw)

    # Log reasoning before converting
    reasoning = data.get("reasoning", "")
    logger.debug("Claude reasoning:\n  %s", reasoning.replace("\n", "\n  "))

    actions = data.get("actions", [])
    print(
        f"[mix_director] plan_transition reasoning: {reasoning[:300].replace(chr(10), ' ')}"
    )
    print(
        f"[mix_director] plan_transition actions ({len(actions)}):\n"
        + "\n".join(f"  {json.dumps(a, separators=(',', ':'))}" for a in actions)
    )

    script = _dict_to_mix_script(data, [t1, t2])
    return script


def direct_mix(analyses: list[TrackAnalysis], model: str, min_minutes: Optional[int] = None, concept: dict | None = None) -> MixScript:
    client = anthropic.Anthropic()
    prompt = build_prompt(analyses, min_minutes)
    if concept:
        d = concept.get("directives", {})
        concept_block = (
            f"{'=' * 60}\n"
            f"ACTIVE CONCEPT: {concept['display_name'].upper()}\n\n"
            f"{concept['prompt_injection']}\n\n"
            f"DIRECTIVES SUMMARY: overlap={d.get('preferred_overlap_bars')} bars | "
            f"technique={d.get('preferred_technique')} | "
            f"bass_swap={d.get('bass_swap_placement')}\n"
            f"{'=' * 60}\n\n"
        )
        prompt = concept_block + prompt

    # System prompt is large and static -- cache it to avoid re-tokenizing on every mix call.
    # max_tokens: 2-track transition JSON is ~800-1200 tokens; 4096 gives headroom.
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": _load_system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage
    print(
        f"[mix_director] direct_mix tokens -- "
        f"in:{usage.input_tokens} (cache_read:{getattr(usage, 'cache_read_input_tokens', 0)} "
        f"cache_write:{getattr(usage, 'cache_creation_input_tokens', 0)}) "
        f"out:{usage.output_tokens}"
    )

    raw = response.content[0].text.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    # Truncated response -- retry once with higher limit
    if response.stop_reason == "max_tokens":
        print("[mix_director] response truncated -- retrying with extended limit")
        followup = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": _load_system_prompt(), "cache_control": {"type": "ephemeral"}}],
            messages=[
                {"role": "user",      "content": prompt},
                {"role": "assistant", "content": response.content[0].text},
                {"role": "user",      "content": "Your response was cut off. Continue and complete the JSON exactly where you left off."},
            ],
        )
        raw = (response.content[0].text + followup.content[0].text).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0].strip()

    data = json.loads(raw)
    return _dict_to_mix_script(data, analyses)


def select_next_track(
    playing: TrackAnalysis,
    candidates: list[TrackAnalysis],
    model: str,
) -> str:
    """
    Ask Claude to pick the best-fitting next track from a list of candidates.
    Returns the candidate's track id (numeric string like "1", "2", ...).
    """
    if not candidates:
        raise ValueError("No candidates to choose from")
    if len(candidates) == 1:
        return candidates[0].id

    client = anthropic.Anthropic()

    def _compact(a: TrackAnalysis) -> dict:
        return {
            "id":         a.id,
            "title":      a.title,
            "bpm":        round(a.bpm, 1),
            "key":        a.key.camelot,
            "energy":     a.energy_overall,
            "duration_s": round(a.duration_s),
        }

    prompt = (
        f"Currently playing: {json.dumps(_compact(playing))}\n\n"
        f"Choose the best next track to mix in from this list:\n"
        f"{json.dumps([_compact(c) for c in candidates], indent=2)}\n\n"
        "Consider harmonic compatibility (Camelot wheel adjacency), BPM proximity "
        "(ideally +-6 BPM, never >15), and energy flow (gradual arc, not random jumps). "
        "Reply with ONLY the chosen track's id, nothing else."
    )

    response = client.messages.create(
        model=model,
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    print(f"[mix_director] select_next_track tokens -- in:{response.usage.input_tokens} out:{response.usage.output_tokens}")
    raw = response.content[0].text.strip().strip('"').strip("'")
    valid_ids = {c.id for c in candidates}
    if raw in valid_ids:
        return raw
    # Claude returned something other than a track ID (title, filename, or garbled output).
    # Log it so it's visible, then fall back to closest BPM.
    fallback = min(candidates, key=lambda c: abs(c.bpm - playing.bpm))
    print(
        f"[mix_director] select_next_track: Claude returned {raw!r} which is not a valid ID "
        f"({sorted(valid_ids)}). Falling back to closest-BPM: {fallback.id} ({fallback.title!r})"
    )
    return fallback.id


def _dict_to_mix_script(data: dict, analyses: list[TrackAnalysis]) -> MixScript:
    # Claude sees stripped filenames in the prompt -- restore full paths from analyses
    path_by_id = {f"T{i+1}": a.file for i, a in enumerate(analyses)}
    # Only pass known MixTrackRef fields — Claude sometimes echoes extra prompt fields
    # (key, key_camelot, duration_s, energy, etc.) that MixTrackRef doesn't accept.
    tracks = []
    for t in data["tracks"]:
        tid = t["id"]
        tracks.append(MixTrackRef(
            id               = tid,
            path             = path_by_id.get(tid, t.get("path", "")),
            bpm              = float(t.get("bpm", 120.0)),
            first_downbeat_s = float(t.get("first_downbeat_s", 0.0)),
        ))
    actions = []
    for a in data["actions"]:
        # normalise: fill missing optional fields with None
        action = MixAction(
            type=a["type"],
            track=a["track"],
            at_bar=a.get("at_bar"),
            from_bar=a.get("from_bar"),
            start_bar=a.get("start_bar"),
            duration_bars=a.get("duration_bars"),
            stems=a.get("stems"),
            bar=a.get("bar"),
            low=a.get("low"),
            mid=a.get("mid"),
            high=a.get("high"),
            eq_duration_bars=a.get("eq_duration_bars"),
            volume=a.get("volume"),
            incoming_track=a.get("incoming_track"),
            loop_bars=a.get("loop_bars"),
            loop_repeats=a.get("loop_repeats"),
            loop_mute_tail=a.get("loop_mute_tail"),
        )
        actions.append(action)

    return MixScript(
        mix_title=data.get("mix_title", f"Claude DJ Set -- {date.today()}"),
        reasoning=data.get("reasoning", ""),
        tracks=tracks,
        actions=actions,
    )
