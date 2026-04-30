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

You are acting as the Claude DJ brain. You will receive structured audio analysis data for a set of tracks and must output a mix script as JSON.

**Section labels may be abstract (A/B/C/…) rather than named (intro/drop/outro).** Do not infer section function from the letter. Use the energy curve and stem presence data to determine what each section is — a section with energy≥8 and drums≥8 is a drop; a low-energy, low-drum section early in the track is an intro. Always reason from the data.

Follow the operational checklist in section 6 of the skill document for every transition. Apply the bass swap protocol from section 3.1 via the `bass_swap` action. Use the stem layering order from section 3.2 via `fade_in` stems. Choose crossfade length per the genre table in section 3.3.

### Transition length — critical for a professional feel

- **Default crossfade: 16 bars.** Use 32 bars for peak-hour or high-energy tracks where a slow blend sounds better. Use 24 bars when energy levels are unequal.
- **Never shorter than 8 bars** except for deliberate cut transitions (and those should be rare).
- The safety layer will snap all `duration_bars` to the nearest phrase multiple (8/16/24/32…) and enforce a minimum of 16 bars — so think in 8-bar chunks and lean toward 16–32.
- Place `fade_in` to start at or just before the incoming track's `mix_in` cue point.
- Place `fade_out` to end at or just after the outgoing track's `mix_out` cue point.
- This naturally produces 16–32 bar overlap windows.

### Set structure — build an energy arc

- **Use most of each track's body.** Start playing from near the track's `mix_in` cue point; let it run until near `mix_out`. Avoid exiting a track at its first breakdown.
- **Build an energy arc across the full set:** warm-up (lower energy, introductory tracks) → peak (highest energy, densest drops) → cooldown (returning to more relaxed energy). Mention the arc shape in your reasoning.
- **Use every track at least once.** If you have 3+ tracks, spend meaningful time on each.
- A 4-track set should typically produce 20–40 minutes of continuous audio. A 2-track set should produce 8–15 minutes.

### Executor behavior (read before designing actions)

The renderer is deliberately conservative — your creative contribution is *when* and *between which sections* transitions happen, not exotic DSP values.

- `play` / `fade_in` / `fade_out` / `eq` operate on **per-track layers** that are summed at the end. A `fade_out` on T1 cannot silence T2. An `eq` on T1 cannot color T2.
- **Every `fade_in` must be followed by a `play` action** for the same track at `start_bar + duration_bars` with `from_bar = fade_in.from_bar + fade_in.duration_bars`. Without it, the track goes silent after the stem intro.
- `bass_swap` is the preferred bass hand-off primitive. Emit it once per transition at a phrase boundary inside the overlap window. It applies a hard 200 Hz high-pass to the **outgoing** track's layer from that bar onward, and restores the incoming track's bass.
- `eq` is for **gentle tilt only** (all values clamped to 0.0–1.0; mid maps to ±6 dB max). Use `low=0.0` only when you need a complete bass kill; prefer `bass_swap` for that instead.
- Stem volumes in `fade_in` control relative levels during the crossfade window. `bass: 0.0` holds the incoming track's bass until the `bass_swap` fires.
- A safety layer clamps all `duration_bars` to [4, 64] and will inject a `bass_swap` and an implied `play` automatically if you omit them — but it's better to place them intentionally.

### Loop actions — extending builds and outros

Use `loop` to repeat a short phrase in place: holds energy at a peak, extends an outro, or builds tension before a drop. Rules:

- `start_bar` must be a phrase boundary (multiple of 8).
- `loop_bars`: 4 or 8 bars only. An 8-bar loop repeating twice = 16 bars of extension.
- `loop_repeats`: 1–4. More than 3 gets fatiguing — use sparingly.
- Place loops on high-energy or build sections, never mid-intro.
- The executor mutes the original track under the loop window so there is no doubling — the loop is a clean phrase replacement, not a layer.
- After the loop ends, continue with a `play` or `fade_out` as normal.

### Output schema

Output ONLY valid JSON. No prose outside the JSON. Put all reasoning in the "reasoning" field.

```json
{
  "mix_title": "string",
  "reasoning": "string — cite checklist items, skill rules, energy arc, and cue point choices for every decision",
  "tracks": [
    {"id": "T1", "path": "string", "bpm": float, "first_downbeat_s": float}
  ],
  "actions": [
    {"type": "play",      "track": "T1", "at_bar": int, "from_bar": int},
    {"type": "loop",      "track": "T1", "start_bar": int, "loop_bars": 8, "loop_repeats": 2},
    {"type": "fade_in",   "track": "T2", "start_bar": int, "duration_bars": int, "from_bar": int,
     "stems": {"drums": float, "bass": float, "vocals": float, "other": float}},
    {"type": "play",      "track": "T2", "at_bar": int, "from_bar": int},
    {"type": "fade_out",  "track": "T1", "start_bar": int, "duration_bars": int},
    {"type": "bass_swap", "track": "T1", "at_bar": int},
    {"type": "eq",        "track": "T1", "bar": int, "low": float, "mid": float, "high": float}
  ]
}
```

All timing is in bars. `stems` values are 0.0–1.0 (volume scalar). `eq` values are 0.0–1.0 (0.0 = full kill, 1.0 = unity). `bass_swap` `at_bar` must be a phrase boundary (multiple of 8) within the transition overlap window. `loop` `start_bar` must be a phrase boundary (multiple of 8).
"""


def _load_system_prompt() -> str:
    if _SKILL_PATH.exists():
        skill = _SKILL_PATH.read_text()
    else:
        import sys
        print(
            f"[mix_director] WARNING: {_SKILL_PATH} not found — "
            "Claude will receive no DJ skill context. Commit dj_skill.md to fix this.",
            file=sys.stderr,
        )
        skill = ""
    return skill + _TASK_PROMPT


def build_prompt(analyses: list[TrackAnalysis], min_minutes: Optional[int] = None) -> str:
    track_dicts = []
    for a in analyses:
        d = a.to_dict()
        # drop raw file paths from sections/stems in prompt (not useful for Claude)
        del d["stems"]
        d["file"] = d["file"].split("/")[-1]
        track_dicts.append(d)

    duration_instruction = ""
    if min_minutes:
        duration_instruction = (
            f"\n\nTARGET SET LENGTH: at least {min_minutes} minutes of continuous audio. "
            "Use as much of each track's body as needed to hit this target. "
            "If the tracks are long enough, extend overlap windows and let tracks play longer before transitioning."
        )

    return (
        f"Here are {len(analyses)} tracks to mix. Analyze the set and output a mix script."
        f"{duration_instruction}\n\n"
        f"TRACKS:\n{json.dumps(track_dicts, indent=2)}\n\n"
        "Output the mix script JSON now."
    )


def direct_mix(analyses: list[TrackAnalysis], model: str, min_minutes: Optional[int] = None) -> MixScript:
    client = anthropic.Anthropic()
    prompt = build_prompt(analyses, min_minutes)

    # System prompt is large (~35 KB) and static — cache it to avoid re-tokenizing
    # on every mix call. Cache TTL is 5 minutes; repeated calls within a session hit it.
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": _load_system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    data = json.loads(raw)
    return _dict_to_mix_script(data, analyses)


def _dict_to_mix_script(data: dict, analyses: list[TrackAnalysis]) -> MixScript:
    tracks = [MixTrackRef(**t) for t in data["tracks"]]
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
        mix_title=data.get("mix_title", f"Claude DJ Set — {date.today()}"),
        reasoning=data.get("reasoning", ""),
        tracks=tracks,
        actions=actions,
    )
