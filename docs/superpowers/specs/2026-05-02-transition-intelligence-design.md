# Transition Intelligence Layer — Design Spec

**Status:** Approved for implementation  
**Date:** 2026-05-02

---

## 1. Problem

The AI DJ makes transition decisions from raw zone data (`d/h/r/onsets` per bar) and section-level stem presence. The model can follow instructions about when to use EQ, loops, and bass swaps — but it lacks the interpretive layer that tells it *why* any given bar is appropriate for a given technique.

Observed failure modes:
- Vocal collisions: two vocals overlapping because the model didn't know exactly which bars T1's vocals ended and T2's began
- Loops placed on vocal or harmonic sections because the model inferred safety from `h` alone, missing the vocal stem
- Phase 1 window selection reasoning from scratch off a 12-bar probe peek, missing the track's full structure
- Derived hints point to bar numbers without explaining the reasoning, so edge cases fall through

**Core shift:** stop giving the model data to interpret. Give it interpretations to act on.

---

## 2. Architecture

Three interlocking changes, touching `schema.py`, `analyze.py`, and `mix_director.py`:

### 2.1 Phase 0 — Track Reading Pass

Runs inside `analyze_tracks()`, after Demucs stem separation, once per track. Produces a `MixingProfile` that is cached in the existing `analysis.json` alongside `TrackAnalysis`. Every subsequent mix using that track gets the profile for free.

Two steps:
1. **Algorithmic computation** — read the full-track vocal stem bar-by-bar; identify vocal regions, loop candidates, transition windows, intro/outro character. Pure Python, no API call.
2. **API interpretation call** — one call to `claude-haiku-4-5` that reads the computed structure and produces a `dj_notes` string: a focused paragraph summarising the track's mixing character in plain language.

### 2.2 Zone Enrichment — Vocals Column

`analyze_transition_zone()` gains a `vocals` column (per-bar vocal stem RMS, 0–1) and inline semantic annotations (`[VOCAL_ACTIVE]`, `[LOOP_SAFE]`, `[LOOP_UNSAFE_VOX]`, `[LOOP_UNSAFE_HARM]`, `[FADE_IN_OK]`). The model reads labels, not numbers.

### 2.3 Richer Derived Hints

`_compute_zone_hints()` is rewritten to use the `MixingProfile`. Every hint gets a "because" clause. `_vocal_warning()` is removed — the new hints do its job and more, surfacing exact EQ timelines, loop-safe windows with reasons, and a technique recommendation derived from the actual zone situation.

---

## 3. Data Model

### 3.1 New dataclasses in `schema.py`

```python
@dataclass
class LoopCandidate:
    start_bar: int
    bars: int        # snapped to valid: 2, 4, 8, 16
    reason: str      # e.g. "drums-only, h=0.04, vocals=0.00, 8 bars clean"

@dataclass
class TransitionWindow:
    bar: int
    quality: int     # 1–10
    character: str   # e.g. "drums-only 16 bars" | "breakdown" | "sparse-post-vocal"

@dataclass
class MixingProfile:
    vocal_bars: list[tuple[int, int]]         # [(start_bar, end_bar), ...]
    loop_candidates: list[LoopCandidate]      # best first
    transition_windows: list[TransitionWindow]  # best first
    intro_type: str   # "drums-only" | "melodic" | "instant-drop" | "silent"
    outro_type: str   # "drums-only" | "cold-stop" | "vocals-to-end" | "fade-silence"
    dj_notes: str     # API-generated mixing brief paragraph
```

`TrackAnalysis` gains one new field:

```python
mixing_profile: Optional[MixingProfile] = None
```

`Optional` so existing cached analyses without the field still deserialize cleanly.

### 3.2 Thresholds

| Signal | Threshold | Meaning |
|--------|-----------|---------|
| `vocals > 0.30` | VOCAL_ACTIVE | Vocal stem present and audible |
| `h < 0.10` | harmonic-safe | Low enough harmonic content to loop |
| `vocals < 0.20` | vocal-safe | Vocal stem absent or very low |
| `drums > 0.25` | drums-active | Kick/percussion present |
| `rms < 0.35` | low-energy | Suitable transition runway |

LOOP_SAFE requires: `h < 0.10` AND `vocals < 0.20` AND `drums > 0.25`.  
FADE_IN_OK requires: `drums > 0.25` AND `h < 0.20` AND `vocals < 0.20`.

---

## 4. Phase 0 — Implementation Detail

### 4.1 `build_mixing_profile(audio_path, bpm, first_downbeat_s, stems, no_stems)` in `analyze.py`

**Vocal map computation:**
- Load the vocal stem (`stems.vocals`) at `ANALYSIS_SR`
- Compute per-bar RMS across the full track
- Any bar with vocal RMS normalised > 0.30 is tagged vocal-active
- Consecutive vocal-active bars are merged into `(start_bar, end_bar)` tuples
- Threshold normalised against the track's vocal peak RMS

**Loop candidate identification:**
- Sliding window over full track: find spans of 4+ consecutive bars satisfying LOOP_SAFE criteria
- Snap window length to nearest valid `_VALID_LOOP_BARS` value (2, 4, 8, 16)
- Score by: length of clean span, how far below harmonic threshold, vocal absence
- Keep top 5, ranked best first

**Transition window ranking:**
- Scan the full track for spans of 8+ consecutive bars where `rms < 0.35` AND `vocals < 0.20`
- Score by: span length, drum activity (drums-only windows score highest), absence of [DROP] following within 8 bars
- Classify character: "drums-only" if drums > 0.25 and h < 0.15; "breakdown" if all stems low; "sparse-melodic" otherwise
- Keep top 3

**Intro/outro classification** (first and last 32 bars):
- `intro_type`: "drums-only" if first 8 bars have drums > 0.25 and h < 0.15 and vocals < 0.20; "melodic" if h > 0.20 in first 8 bars; "instant-drop" if rms > 0.60 from bar 0; "silent" if rms < 0.10
- `outro_type`: "drums-only" if last 16 bars have drums > 0.20 and h < 0.15 and vocals < 0.20; "vocals-to-end" if any of last 16 bars are VOCAL_ACTIVE; "cold-stop" if last 4 bars rms < 0.05; "fade-silence" otherwise

**If `no_stems=True`:** skip the vocal map (set `vocal_bars=[]`), skip vocal annotations, still compute transition windows and intro/outro from mix audio. Mark `dj_notes` with "[stems unavailable — vocal analysis skipped]".

### 4.2 `dj_notes` API call

Model: `claude-haiku-4-5-20251001`

System: *"You are a DJ reading a track before playing it. Given structured analysis data, write a concise mixing brief (3-5 sentences) describing: where vocals are active and what to avoid, the best transition-out window and why, any strong loop candidates, and one sentence on the track's overall character for mixing. Be specific about bar numbers."*

User content: JSON of the computed `MixingProfile` fields (excluding `dj_notes`) plus the track's title, BPM, key, duration, and section summary.

Output: a plain string, stored as `dj_notes`. Max 200 tokens.

### 4.3 Caching

Phase 0 is called at the end of `analyze_track()`, after stem separation, before writing `analysis.json`. The `MixingProfile` (including `dj_notes`) is serialized into `analysis.json` under key `"mixing_profile"`. Cache is already hash-based via `file_hash()` — no new cache logic needed. If `analysis.json` already contains `"mixing_profile"`, Phase 0 is skipped entirely.

---

## 5. Zone Enrichment

### 5.1 `analyze_transition_zone()` signature change

```python
def analyze_transition_zone(
    audio_path: str,
    bpm: float,
    first_downbeat_s: float,
    start_bar: int,
    n_bars: int = 48,
) -> list[dict]:
```

Signature unchanged. The vocal stem is located via `file_hash(audio_path)` → cache dir → `stems/vocals.wav`, same pattern as the existing drums/bass/other stem loading. Falls back gracefully if vocals stem absent.

### 5.2 New row schema

```python
{
    "bar": 72,
    "drums": 0.71,
    "harmonic": 0.04,
    "rms": 0.42,
    "onsets": 2,
    "vocals": 0.08,           # NEW — 0.0 if stem unavailable
    "tags": ["LOOP_SAFE"]     # NEW — list of applicable annotations
}
```

**Tag assignment logic:**
```
VOCAL_ACTIVE    if vocals > 0.30
LOOP_SAFE       if h < 0.10 AND vocals < 0.20 AND drums > 0.25
LOOP_UNSAFE_VOX if vocals > 0.30
LOOP_UNSAFE_HARM if h > 0.15
FADE_IN_OK      if drums > 0.25 AND h < 0.20 AND vocals < 0.20
```

Only the most relevant tags are shown (LOOP_SAFE and LOOP_UNSAFE_* are mutually exclusive).

### 5.3 Zone table display

Tags appended to the row's display string in the prompt zone table:

```
b 72: d=0.71 h=0.04 r=0.42 on=2 vox=0.08  [LOOP_SAFE]
b 73: d=0.65 h=0.03 r=0.44 on=2 vox=0.61  [VOCAL_ACTIVE] [LOOP_UNSAFE_VOX]
b 74: d=0.70 h=0.05 r=0.43 on=3 vox=0.72  [VOCAL_ACTIVE] [LOOP_UNSAFE_VOX]
```

---

## 6. Richer Derived Hints

### 6.1 `_compute_zone_hints(t1_zone, t2_zone, t1_profile, t2_profile)` — new signature

Takes both zone lists and both `MixingProfile` objects (may be `None`).

### 6.2 Hint blocks produced

**Vocal sequencing block** (generated when either track has vocals in zone):

```
VOCAL SITUATION:
  T1 vocals active until bar 76 (last [VOCAL_ACTIVE] bar in T1 exit zone)
  T2 vocals enter at bar 10 (first [VOCAL_ACTIVE] bar in T2 entry zone)
  → eq(T1, bar=72, mid=0.3)  — cut T1 mids 4 bars before T1 vocals end
  → Do NOT restore T1 mid — vocals would re-emerge into the blend
  → T1 mids must reach ≤ 0.3 before T2 bar 10
  → Maximum safe overlap: 18 bars before vocal collision
```

**Bass swap hint with "because" clause:**

```
T1 preferred bass_swap: bar 88
  BECAUSE: d+h=0.08 (lowest in exit zone), T1 in BREAKDOWN section,
  T2 drums active b0–b8 (d>0.25), T2 harmonic enters bar 12,
  vocals clear both sides (T1 vocal end=76, T2 vocal start=24)
```

**Loop candidates block:**

```
LOOP CANDIDATES in T1 exit zone:
  ✓ bars 80–88: LOOP_SAFE (h=0.03, vocals=0.00, drums=0.74) — 8 bars clean
  ✗ bars 64–72: LOOP_UNSAFE_VOX (vocals=0.68) — active vocal, do not loop
  ✗ bars 72–80: LOOP_UNSAFE_HARM (h=0.22) — harmonic content present
```

**Technique recommendation block:**

```
RECOMMENDED TECHNIQUE: blend, 32 bars
  BECAUSE: T1 outro clean 16+ bars, Camelot dist=1, ΔBPM=0.5,
  T1 vocals end bar 76 (20 bars of clean runway), T2 drums-only intro
  AVOID: loop on any [LOOP_UNSAFE_*] bar; fade_in before T2 bar 0 (instant-drop entry)
```

### 6.3 `_vocal_warning()` removed

Its functionality is fully covered by the vocal sequencing block above, which is more precise (exact bar numbers) and actionable (specific EQ values and timing).

### 6.4 `_PLAN_TASK_SUFFIX` addition

One rule appended:

```
**3. Loop placement rule**
loop.start_bar MUST reference a bar annotated [LOOP_SAFE] in the zone table above.
Never place a loop on a bar annotated [LOOP_UNSAFE_VOX] or [LOOP_UNSAFE_HARM].
```

---

## 7. Phase 1 Injection

`select_transition_window()` gains both tracks' mixing profiles as input. When profiles are available, the 12-bar probe peek is supplemented (not replaced) by a mixing profile summary block:

```
T1 MIXING PROFILE:
  intro: drums-only | outro: drums-only (bar 96–112, 16 bars clean)
  vocals: bars 16–48, 64–80 — avoid for transition windows
  best exit windows: bar 96 (quality=9), bar 80 (quality=6)
  DJ notes: "Clean percussion outro from bar 96..."

T2 MIXING PROFILE:
  intro: drums-only (bar 0–8) | first harmonic: bar 8 | first vocal: bar 24
  best entry window: bar 0 (quality=9)
```

Phase 1's `_WINDOW_PROMPT_TEMPLATE` gains a `{profiles_section}` slot. If profiles are absent (e.g. `no_stems=True` with no cached profile), the slot is empty and behaviour is unchanged.

---

## 8. Files Changed

| File | Change |
|------|--------|
| `claude-dj/schema.py` | Add `LoopCandidate`, `TransitionWindow`, `MixingProfile`; add `mixing_profile: Optional[MixingProfile]` to `TrackAnalysis` |
| `claude-dj/analyze.py` | Add `build_mixing_profile()`; call from `analyze_track()`; extend `analyze_transition_zone()` with vocals column + tags |
| `claude-dj/mix_director.py` | Rewrite `_compute_zone_hints()` with vocal/loop/technique hint blocks; remove `_vocal_warning()`; update `select_transition_window()` to inject profiles; update `_format_plan_prompt()` to pass profiles to hints; add loop placement rule to `_PLAN_TASK_SUFFIX`; update `_format_zone_table()` to display vocals + tags |
| `claude-dj/tests/test_mixing_profile.py` | New: algorithmic profile computation tests |
| `claude-dj/tests/test_zone_enrichment.py` | New: vocals column + tag annotation tests |
| `claude-dj/tests/test_derived_hints.py` | New: hint output tests given mock zone data |

`cli.py`, `normalizer.py`, `executor.py`, `concept_bank/` — **unchanged**.

---

## 9. Out of Scope

- Changing the `MixAction` schema or executor
- Re-running analysis on already-cached tracks (user must delete cache to trigger Phase 0)
- BPM or key detection changes
- Frontend changes
