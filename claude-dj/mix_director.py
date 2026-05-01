from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic

from schema import MixAction, MixScript, MixTrackRef, TrackAnalysis

_SKILL_PATH = Path(__file__).parent / "dj_skill.md"

_TASK_PROMPT = """
---

## YOUR TASK

You are acting as the Claude DJ brain. You will receive structured audio analysis for a set of tracks and must output a professional mix script as JSON.

Tracks now include **semantic section labels** (intro / groove / breakdown / drop / outro) derived from energy and stem analysis. Use them directly.

Follow the operational checklist in section 6 of the skill document for every transition. Apply the bass swap from section 3.1 via `bass_swap`. Use stem layering from section 3.2 via `fade_in` stems. Choose crossfade length from section 3.3.

---

### HOW TO READ THE TRACK DATA

Each track summary includes:

```
SECTIONS: INTRO(b0-16,e=3,drums) -> GROOVE(b16-48,e=7,drums+bass+other) -> BREAKDOWN(b48-64,e=4,other) -> DROP(b64-96,e=9,drums+bass+vox+other) -> OUTRO(b96-112,e=4,drums)
CUES:     mix_in=b16  drop_bar=b64  breakdown_start=b48  mix_out=b96
ENERGY CURVE: [........]
```

**Using sections to pick transition windows:**

| You want to...            | Look for on T1 (outgoing)       | Look for on T2 (incoming)             |
|---------------------------|---------------------------------|---------------------------------------|
| Standard blend            | OUTRO or BREAKDOWN section      | Start of INTRO                        |
| Energy drop               | BREAKDOWN -> use as T1 exit     | INTRO of lower-energy track           |
| Energy rise               | End of T1's OUTRO               | T2's GROOVE or DROP entry             |
| Key-clash escape          | Drum-only portion of OUTRO      | INTRO (drums only, no harmonic content)|

**Critical reading rules:**
- `mix_in` cue = where T2 should START playing (its intro, the DJ-friendly entry point)
- `mix_out` cue = where T1's outro begins -- start T1's `fade_out` here or slightly before
- `breakdown_start` = ideal T1 exit window for smooth transitions (sparse, low-density)
- `drop_bar` = DO NOT start a transition here; it's the audience-payoff section

---

### TRANSITION WINDOW SELECTION

**Step 1 -- Find T1's exit window:**
  - Best: T1's OUTRO section (cleanest percussion, designed for DJ mixing)
  - Good: T1's last BREAKDOWN (sparse, low-density, room for T2 to enter)
  - Emergency: last GROOVE section if no OUTRO/BREAKDOWN exists

**Step 2 -- Find T2's entry point:**
  - Always: T2's INTRO start (= `mix_in` cue). Intro is drum/percussion-only or sparse.
  - Never: T2's DROP or main GROOVE (too dense, no headroom for T1)

**Step 3 -- Overlap duration:**
  - T1 OUTRO -> T2 INTRO: 16-32 bars (standard)
  - T1 BREAKDOWN -> T2 INTRO: 24-32 bars (slower, melodic blend)
  - Key clash: reduce to 8 bars, drums-only stems on T2

**Step 4 -- Bass swap:**
  - Place at the first 8-bar phrase boundary after T2's fade_in starts
  - T2's `fade_in` stems: `bass: 0.0` until the swap fires
  - After the swap, T1's bass is gone, T2's bass is in

---

### TRANSITION LENGTH -- CRITICAL

- **Default overlap: 16 bars.** Use 32 for deep/progressive styles; 8 for cuts or key-clashes.
- **Never shorter than 8 bars** unless a deliberate cut (note in reasoning).
- Safety layer snaps `duration_bars` to phrase multiples (8/16/24/32) with minimum 16 bars.
- T2 `fade_in.start_bar` + `duration_bars` = T2 `play.at_bar` (must match exactly).
- T1 `fade_out.start_bar` = same as T2's `fade_in.start_bar` (simultaneous crossfade).

---

### SET STRUCTURE -- ENERGY ARC

- Play T1 from its `mix_in` cue through to near its `mix_out` cue.
- **Do not exit T1 at its first BREAKDOWN.** Let T1 run at least through one DROP before transitioning.
- Build an energy arc: note whether the set rises, holds, or descends in reasoning.
- A 2-track set: 8-15 min. A 4-track set: 20-40 min.

---

### EXECUTOR BEHAVIOR

- `play` / `fade_in` / `fade_out` / `eq` act on **per-track layers** summed at output.
- **Every `fade_in` MUST be followed by a `play`** at `start_bar + duration_bars` with
  `from_bar = fade_in.from_bar + duration_bars`. Without the `play`, T2 goes silent.
- `bass_swap` cuts T1's low band (<=200 Hz) to silence and restores T2's bass. **MANDATORY on
  every blend transition**: omitting it means BOTH kick drums play simultaneously — instant mud.
  Fire ONCE per transition at a phrase boundary (multiple of 8) inside the overlap window, after
  T2's fade_in is ~50% complete. Pre-fade: T1 full bass, T2 bass=0.0 in stems. Post-swap: T1
  bass killed, T2 full bass. This is non-negotiable for a clean mix.
- `eq`: `low` controls a continuous HPF cutoff — low=1.0 is bypass, low=0.5 cuts below ~80 Hz
  (sub-bass only), low=0.0 cuts below 200 Hz (full bass removed). `high` is a shelf at 8 kHz
  (1.0=unity, 0.0=−12 dB). `mid` is a ±6 dB broadband trim. Use low=0.3–0.5 for a gentle
  bass trim; reserve low=0.0 only for a full bass kill. **Never have both T1 and T2 at low=1.0
  simultaneously during the blend window** — at least one must have bass reduced or use bass_swap.
- `loop`: extend an outro or hold a peak phrase.
  RULES: `start_bar` MUST be a multiple of 8. Use 4- or 8-bar loops only. 1-3 repeats max.
  MECHANICS: after the loop, the track automatically resumes from source bar
  `start_bar + loop_bars * loop_repeats`. What this means for what follows:
    - Fade-out (typical): `fade_out` at `start_bar: (start_bar + loop_bars * loop_repeats)`.
    - Drop/continue: emit NO play -- the drop fires at the right time automatically.
      Exception: if you looped 2+ repeats and need to re-enter an earlier source bar,
      add `play` with `from_bar = start_bar + loop_bars` (one phrase past the loop start).
    - T2 fade_in CAN begin inside the loop window -- looping T1 creates stable runway for T2.
  DO NOT place loop and fade_out on the same bar for the same track.

---

### OUTPUT SCHEMA

Output ONLY valid JSON. No prose outside it. Use `reasoning` for concise notes (3-5 sentences
max -- cite specific section labels, bar numbers, key move, energy arc, and bass swap placement).

```json
{
  "mix_title": "string",
  "reasoning": "string",
  "tracks": [
    {"id": "T1", "path": "string", "bpm": 128.0, "first_downbeat_s": 0.5}
  ],
  "actions": [
    {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 16},
    {"type": "fade_in",   "track": "T2", "start_bar": 80, "duration_bars": 16, "from_bar": 0,
     "stems": {"drums": 0.8, "bass": 0.0, "vocals": 0.0, "other": 0.6}},
    {"type": "bass_swap", "track": "T1", "at_bar": 88},
    {"type": "play",      "track": "T2", "at_bar": 96, "from_bar": 16},
    {"type": "fade_out",  "track": "T1", "start_bar": 88, "duration_bars": 16},
    {"type": "loop",      "track": "T1", "start_bar": 64, "loop_bars": 8, "loop_repeats": 2},
    {"type": "eq",        "track": "T2", "bar": 96, "low": 0.5, "mid": 1.0, "high": 1.0}
  ]
}
```

All bar values are absolute. `stems` scalars 0.0-1.0. `eq` values 0.0-1.0 (0=kill, 1=unity).
`bass_swap.at_bar` and `loop.start_bar` must be multiples of 8.
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

_WINDOW_PROMPT_TEMPLATE = """\
Given these two track summaries, choose the optimal transition window.

{summaries}

Output a single JSON object:
{{
  "t1_exit_bar":  <int: bar in T1 where fade_out starts — use its mix_out or breakdown_start cue>,
  "t2_enter_bar": <int: bar in T2 where T2 starts fading in — use its mix_in cue (usually 0)>,
  "window_bars":  <int: overlap length, one of 8 / 16 / 24 / 32>,
  "style":        <"blend" | "cut" | "drop_swap">
}}

Rules:
- t1_exit_bar should be T1's mix_out cue (or breakdown_start for a slower blend).
- t2_enter_bar should be T2's mix_in cue (usually 0 — the clean intro start).
- window_bars default = 16. Use 32 for deep/prog styles; 8 for key clashes or tight cuts.
- style = "blend" for standard crossfades, "cut" for instant switches, "drop_swap" for matching drops.
"""


def select_transition_window(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    model: str,
) -> dict:
    """
    Phase 1: lightweight API call (~300 in / ~50 out tokens) that picks where the
    transition should happen.  Returns a dict with t1_exit_bar, t2_enter_bar,
    window_bars, style.  Falls back to cue-point defaults on any error.
    """
    summaries = (
        _format_track_summary(t1, "T1") + "\n\n" + _format_track_summary(t2, "T2")
    )
    prompt = _WINDOW_PROMPT_TEMPLATE.format(summaries=summaries)

    # Sensible defaults derived from cue points
    cue_t1 = {c.name: c.bar for c in t1.cue_points}
    cue_t2 = {c.name: c.bar for c in t2.cue_points}
    default = {
        "t1_exit_bar":  cue_t1.get("mix_out") or cue_t1.get("breakdown_start") or max(0, t1.bar_grid.n_bars - 32),
        "t2_enter_bar": cue_t2.get("mix_in", 0),
        "window_bars":  16,
        "style":        "blend",
    }

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=128,
            system=[{"type": "text", "text": _WINDOW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        print(
            f"[mix_director] select_window tokens -- "
            f"in:{usage.input_tokens} (cache_read:{getattr(usage, 'cache_read_input_tokens', 0)}) "
            f"out:{usage.output_tokens}"
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        window = json.loads(raw)
        # Validate / clamp
        window.setdefault("t1_exit_bar",  default["t1_exit_bar"])
        window.setdefault("t2_enter_bar", default["t2_enter_bar"])
        window["window_bars"] = max(8, min(32, int(window.get("window_bars", 16))))
        window["style"]       = window.get("style", "blend")
        # Ensure t1_exit_bar is a phrase-multiple (multiple of 8)
        window["t1_exit_bar"] = (int(window["t1_exit_bar"]) // 8) * 8
        window["t2_enter_bar"] = max(0, int(window["t2_enter_bar"]))
        return window
    except Exception as exc:
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


def _format_zone_table(zone: list[dict], track_id: str, label: str) -> str:
    """
    Render a compact per-bar zone table for injection into the planning prompt.
    Example row:
      b 80: d=0.82 h=0.71 r=0.75 bright onsets=4
    """
    if not zone:
        return f"{track_id} {label}: (no zone data)\n"

    first_bar = zone[0]["bar"]
    last_bar  = zone[-1]["bar"]
    lines = [f"{track_id} {label} (bars {first_bar}–{last_bar}):"]

    prev = None
    for row in zone:
        brightness = "bright" if row["brightness"] > 0.55 else ("mid" if row["brightness"] > 0.30 else "dark ")
        annotation = _annotate_bar(row, prev)
        lines.append(
            f"  b{row['bar']:3d}: d={row['drums']:.2f} h={row['harmonic']:.2f} "
            f"r={row['rms']:.2f} {brightness} onsets={row['onsets']}{annotation}"
        )
        prev = row

    return "\n".join(lines)


_PLAN_TASK_SUFFIX = """
---

### ZONE DATA

You have been given per-bar measurements for the transition windows of both tracks.

**d** = drums proxy (0=silent, 1=full kick)  
**h** = harmonic proxy (0=silent, 1=full bass+melody)  
**r** = overall RMS (loudness)  
**onsets** = beat density 0–4  
Annotations: [DROP] [BREAKDOWN] [SILENT] [KICK-IN] [BASS-IN] [KICK-OUT] [BASS-OUT]

Use the zone data to place actions precisely:
- `bass_swap` at a bar labelled [KICK-OUT] or lowest d+h point in T1's zone
- T2 `fade_in` starting when T2's zone shows drums before bass ([KICK-IN] before [BASS-IN])
- T1 `fade_out` starting at T1's [KICK-OUT] or [BREAKDOWN] label

The suggested window (`t1_exit_bar`, `t2_enter_bar`, `window_bars`) is a starting point —
adjust ±8 bars to land on cleaner phrase boundaries visible in the zone data.
"""


def _format_plan_prompt(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
) -> str:
    summaries = (
        _format_track_summary(t1, "T1") + "\n\n" + _format_track_summary(t2, "T2")
    )
    t1_table = _format_zone_table(t1_zone, "T1", "exit zone")
    t2_table = _format_zone_table(t2_zone, "T2", "entry zone")

    return (
        "You are planning a 2-track transition.\n\n"
        f"{summaries}\n\n"
        f"Suggested window: T1 exits ~bar {window['t1_exit_bar']}, "
        f"T2 enters ~bar {window['t2_enter_bar']}, overlap ~{window['window_bars']} bars, "
        f"style={window['style']}\n\n"
        f"{t1_table}\n\n"
        f"{t2_table}\n\n"
        "Using the zone data above, output the mix script JSON now."
    )


def plan_transition(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
    model: str,
) -> MixScript:
    """
    Phase 2: full move planning with per-bar zone data injected into the prompt.
    Uses the same output schema as direct_mix.
    """
    client = anthropic.Anthropic()
    system_text = _load_system_prompt() + _PLAN_TASK_SUFFIX
    prompt = _format_plan_prompt(t1, t2, t1_zone, t2_zone, window)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage
    print(
        f"[mix_director] plan_transition tokens -- "
        f"in:{usage.input_tokens} (cache_read:{getattr(usage, 'cache_read_input_tokens', 0)} "
        f"cache_write:{getattr(usage, 'cache_creation_input_tokens', 0)}) "
        f"out:{usage.output_tokens}"
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    if response.stop_reason == "max_tokens":
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
    return _dict_to_mix_script(data, [t1, t2])


def direct_mix(analyses: list[TrackAnalysis], model: str, min_minutes: Optional[int] = None) -> MixScript:
    client = anthropic.Anthropic()
    prompt = build_prompt(analyses, min_minutes)

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
    chosen_id = response.content[0].text.strip().strip('"').strip("'")
    valid_ids = {c.id for c in candidates}
    if chosen_id not in valid_ids:
        # fallback: pick closest BPM
        chosen_id = min(candidates, key=lambda c: abs(c.bpm - playing.bpm)).id
    return chosen_id


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
