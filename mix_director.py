from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import anthropic

from schema import MixAction, MixScript, MixTrackRef, TrackAnalysis

_SKILL_PATH = Path(__file__).parent / "dj_skill.md"

_TASK_PROMPT = """
---

## YOUR TASK

You are acting as the Claude DJ brain. You will receive structured audio analysis data for a set of tracks and must output a mix script as JSON.

**Section labels may be abstract (A/B/C/…) rather than named (intro/drop/outro).** Do not infer section function from the letter. Use the energy curve and stem presence data to determine what each section is — a section with energy≥8 and drums≥8 is a drop; a low-energy, low-drum section early in the track is an intro. Always reason from the data.

Follow the operational checklist in section 6 of the skill document for every transition. Apply the bass swap protocol from section 3.1. Use the stem layering order from section 3.2. Choose crossfade length per the genre table in section 3.3.

Output ONLY valid JSON matching this schema. No prose outside the JSON. Put all reasoning in the "reasoning" field.

```
{
  "mix_title": "string",
  "reasoning": "string — cite checklist items and skill rules for every decision",
  "tracks": [
    {"id": "T1", "path": "string", "bpm": float, "first_downbeat_s": float}
  ],
  "actions": [
    {"type": "play",     "track": "T1", "at_bar": int, "from_bar": int},
    {"type": "fade_in",  "track": "T2", "start_bar": int, "duration_bars": int,
     "stems": {"drums": float, "bass": float, "vocals": float, "other": float}},
    {"type": "eq",       "track": "T1", "bar": int, "low": float, "mid": float, "high": float},
    {"type": "fade_out", "track": "T1", "start_bar": int, "duration_bars": int}
  ]
}
```

All timing is in bars. stems values are 0.0–1.0 (volume scalar). eq values are 0.0–1.0 gain (0.0 = full kill, 1.0 = unity).
"""


def _load_system_prompt() -> str:
    skill = _SKILL_PATH.read_text() if _SKILL_PATH.exists() else ""
    return skill + _TASK_PROMPT


def build_prompt(analyses: list[TrackAnalysis]) -> str:
    track_dicts = []
    for a in analyses:
        d = a.to_dict()
        # drop raw file paths from sections/stems in prompt (not useful for Claude)
        del d["stems"]
        d["file"] = d["file"].split("/")[-1]
        track_dicts.append(d)

    return (
        f"Here are {len(analyses)} tracks to mix. Analyze the set and output a mix script.\n\n"
        f"TRACKS:\n{json.dumps(track_dicts, indent=2)}\n\n"
        "Output the mix script JSON now."
    )


def direct_mix(analyses: list[TrackAnalysis], model: str) -> MixScript:
    client = anthropic.Anthropic()
    prompt = build_prompt(analyses)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_load_system_prompt(),
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
        )
        actions.append(action)

    return MixScript(
        mix_title=data.get("mix_title", f"Claude DJ Set — {date.today()}"),
        reasoning=data.get("reasoning", ""),
        tracks=tracks,
        actions=actions,
    )
