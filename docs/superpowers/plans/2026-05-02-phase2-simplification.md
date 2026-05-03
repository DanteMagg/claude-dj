# Phase 2 Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase 2's information-overloaded prompt with a stripped 4-rule prompt and move constraint enforcement into the normalizer so Claude can't break it.

**Architecture:** Three parallel tracks: (1) normalizer gets four new enforcement passes run before existing passes, (2) executor gets a test confirming existing slip-mode loop behavior is correct, (3) mix_director loses `_compute_zone_hints()` and the examples block and gains a compact `_format_situation_summary()` + inline rules. Phase 0 and Phase 1 are untouched.

**Tech Stack:** Python 3.10+, pytest, pydub (executor tests), dataclasses

---

## File Map

| File | What changes |
|---|---|
| `claude-dj/normalizer.py` | Add `_enforce_t2_bass_zero`, `_inject_eq_duration`, `_snap_fade_in_anchor`; update `_VALID_LOOP_BARS` to include 1; wire all into `normalize()` |
| `claude-dj/executor.py` | No code changes — tests verify existing slip-mode is correct |
| `claude-dj/mix_director.py` | Delete `_compute_zone_hints()`; add `_format_situation_summary()` and `_trim_zone()`; rewrite `_format_plan_prompt()`; set `_PLAN_TASK_SUFFIX = ""` |
| `claude-dj/tests/test_normalizer_enforcement.py` | New: 9 tests for the four new normalizer rules |
| `claude-dj/tests/test_executor_slip_mode.py` | New: 4 tests confirming slip-mode loop behaviour |

---

## Task 1: Normalizer — T2 bass=0 enforcement and EQ duration injection

**Files:**
- Modify: `claude-dj/normalizer.py`
- Create: `claude-dj/tests/test_normalizer_enforcement.py`

- [ ] **Step 1: Write the failing tests**

```python
# claude-dj/tests/test_normalizer_enforcement.py
import pytest
from normalizer import normalize
from schema import MixAction, MixScript, MixTrackRef


def _script(actions, n_tracks=2):
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=128.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


# ── T2 bass=0 enforcement ──────────────────────────────────────────────────


def test_t2_fade_in_bass_forced_to_zero():
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16,
                  stems={"drums": 0.8, "bass": 0.9, "other": 0.6}),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems["bass"] == 0.0


def test_t2_fade_in_bass_zero_already_unchanged():
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16,
                  stems={"drums": 0.8, "bass": 0.0, "other": 0.6}),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems["bass"] == 0.0


def test_t2_fade_in_no_stems_unaffected():
    # fade_in with no stems dict — should not crash
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems is None


# ── EQ duration injection ──────────────────────────────────────────────────


def test_eq_duration_injected_when_missing():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
        MixAction(type="eq",       track="T1", bar=16,    low=0.0),   # no eq_duration_bars
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16),
    ])
    result = normalize(s)
    eq_a = next(a for a in result.actions if a.type == "eq" and a.track == "T1")
    assert eq_a.eq_duration_bars == 4


def test_eq_duration_not_overwritten_when_present():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
        MixAction(type="eq",       track="T1", bar=16,    low=0.0, eq_duration_bars=2),
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16),
    ])
    result = normalize(s)
    eq_a = next(a for a in result.actions if a.type == "eq" and a.track == "T1")
    assert eq_a.eq_duration_bars == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/test_normalizer_enforcement.py -v 2>&1 | head -30
```

Expected: FAIL — `_enforce_t2_bass_zero` and `_inject_eq_duration` not defined yet.

- [ ] **Step 3: Implement the two new normalizer functions**

Open `claude-dj/normalizer.py`. Add both functions after `_clamp_eq` (around line 120):

```python
def _enforce_t2_bass_zero(actions: list[MixAction]) -> list[MixAction]:
    """T2's fade_in must never introduce bass. Force stems["bass"]=0.0 if set."""
    result = []
    for a in actions:
        if a.type == "fade_in" and a.stems and a.stems.get("bass", 0.0) > 0.0:
            msg = f"forced stems.bass=0.0 on fade_in({a.track}) (was {a.stems['bass']:.2f})"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, stems={**a.stems, "bass": 0.0})
        result.append(a)
    return result


def _inject_eq_duration(actions: list[MixAction]) -> list[MixAction]:
    """Any eq action missing eq_duration_bars gets the default ramp of 4 bars."""
    result = []
    for a in actions:
        if a.type == "eq" and a.eq_duration_bars is None:
            msg = f"injected eq_duration_bars=4 on eq({a.track} bar={a.bar})"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, eq_duration_bars=4)
        result.append(a)
    return result
```

Wire them into `normalize()`. Change:

```python
    actions = _clamp_durations(actions)
    actions = _clamp_eq(actions)
    actions = _clamp_loops(actions)
    actions = _snap_bass_swap_bars(actions)
```

To:

```python
    actions = _clamp_durations(actions)
    actions = _clamp_eq(actions)
    actions = _clamp_loops(actions)
    actions = _enforce_t2_bass_zero(actions)
    actions = _inject_eq_duration(actions)
    actions = _snap_bass_swap_bars(actions)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/test_normalizer_enforcement.py::test_t2_fade_in_bass_forced_to_zero tests/test_normalizer_enforcement.py::test_t2_fade_in_bass_zero_already_unchanged tests/test_normalizer_enforcement.py::test_t2_fade_in_no_stems_unaffected tests/test_normalizer_enforcement.py::test_eq_duration_injected_when_missing tests/test_normalizer_enforcement.py::test_eq_duration_not_overwritten_when_present -v
```

Expected: 5 PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -q
```

Expected: all existing tests still pass (99+ passing).

- [ ] **Step 6: Commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add claude-dj/normalizer.py claude-dj/tests/test_normalizer_enforcement.py
git commit -m "feat: normalizer enforces T2 bass=0 and EQ ramp duration"
```

---

## Task 2: Normalizer — 1-bar loops and anchor-first ×8 phrase snapping

**Files:**
- Modify: `claude-dj/normalizer.py`
- Modify: `claude-dj/tests/test_normalizer_enforcement.py`

- [ ] **Step 1: Add tests for 1-bar loops and anchor snapping**

Append to `claude-dj/tests/test_normalizer_enforcement.py`:

```python
# ── 1-bar loop support ─────────────────────────────────────────────────────


def test_one_bar_loop_preserved():
    s = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=80, loop_bars=1, loop_repeats=4),
        MixAction(type="fade_out", track="T1", start_bar=88, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=88, duration_bars=16),
    ])
    result = normalize(s)
    loop_a = next(a for a in result.actions if a.type == "loop")
    assert loop_a.loop_bars == 1


# ── Anchor-first ×8 phrase snapping ───────────────────────────────────────


def test_fade_in_snapped_to_phrase_boundary():
    s = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_out",  track="T1", start_bar=20, duration_bars=16),
        MixAction(type="fade_in",   track="T2", start_bar=20, duration_bars=16),
        MixAction(type="bass_swap", track="T1", at_bar=28, incoming_track="T2"),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.start_bar % 8 == 0


def test_bass_swap_offset_preserved_after_anchor_snap():
    # fade_in at bar 20 → snaps to 16 (delta=-4)
    # bass_swap was 8 bars after fade_in (bar 28) → should be 8 bars after snapped (bar 24)
    s = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_out",  track="T1", start_bar=20, duration_bars=16),
        MixAction(type="fade_in",   track="T2", start_bar=20, duration_bars=16),
        MixAction(type="bass_swap", track="T1", at_bar=28, incoming_track="T2"),
    ])
    result = normalize(s)
    swap = next(a for a in result.actions if a.type == "bass_swap")
    fi   = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    # bass_swap must be after fade_in (no collision)
    assert swap.at_bar > fi.start_bar
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/test_normalizer_enforcement.py::test_one_bar_loop_preserved tests/test_normalizer_enforcement.py::test_fade_in_snapped_to_phrase_boundary tests/test_normalizer_enforcement.py::test_bass_swap_offset_preserved_after_anchor_snap -v
```

Expected: `test_one_bar_loop_preserved` FAIL (1 snaps to 2 currently), `test_fade_in_snapped_to_phrase_boundary` FAIL (no anchor snapping), `test_bass_swap_offset_preserved_after_anchor_snap` FAIL.

- [ ] **Step 3: Update `_VALID_LOOP_BARS` to include 1**

In `claude-dj/normalizer.py`, change line ~84:

```python
_VALID_LOOP_BARS = (1, 2, 4, 8, 16, 32)
```

Also update `_snap_loop_bars` to allow 1-bar minimum:

```python
def _snap_loop_bars(bars: int) -> int:
    """Snap to nearest valid loop length. Minimum is 1 bar."""
    bars = max(1, bars)
    return min(_VALID_LOOP_BARS, key=lambda v: (abs(v - bars), -v))
```

Also update `_clamp_loops` — the `start_bar` snap line currently snaps to `PHRASE` (8). Change it to snap to the nearest multiple of `PHRASE` but using the loop_bars as the unit (a 1-bar loop should start at any bar, a 2-bar loop at any even bar, an 8-bar loop at ×8). For simplicity: snap start_bar to `loop_bars` boundary:

```python
def _clamp_loops(actions: list[MixAction]) -> list[MixAction]:
    """Snap loop_bars to valid values; cap loop_repeats to [1, 8]."""
    result = []
    for a in actions:
        if a.type != "loop":
            result.append(a)
            continue
        lb    = _snap_loop_bars(a.loop_bars or 4)
        reps  = max(1, min(8, a.loop_repeats or 1))
        start = (a.start_bar or 0) // lb * lb   # align to loop_bars boundary
        result.append(dataclasses.replace(a, loop_bars=lb, loop_repeats=reps, start_bar=start))
    return result
```

- [ ] **Step 4: Add `_snap_fade_in_anchor` after `_snap_bass_swap_bars`**

Add this function in `claude-dj/normalizer.py`, after `_snap_bass_swap_bars`:

```python
def _snap_fade_in_anchor(actions: list[MixAction]) -> list[MixAction]:
    """
    Snap each fade_in.start_bar to the nearest ×PHRASE boundary.
    Co-shift all subsequent actions on the same track AND any bass_swap
    within a 40-bar window by the same delta, so relative offsets are preserved.

    Must run before _snap_bass_swap_bars to prevent independent snapping
    from creating a zero-gap between fade_in and bass_swap.
    """
    result = list(actions)

    for fi in [a for a in actions if a.type == "fade_in" and a.start_bar is not None]:
        orig    = fi.start_bar
        snapped = round(orig / PHRASE) * PHRASE
        delta   = snapped - orig
        if delta == 0:
            continue

        tid = fi.track
        msg = f"anchor-snapped fade_in({tid}) start_bar {orig}→{snapped} (Δ{delta:+d})"
        logger.debug("NORMALIZER FIX: %s", msg)
        print(f"[normalizer] {msg}")

        new_result = []
        for a in result:
            if a.track == tid:
                if a.type == "fade_in" and a.start_bar == orig:
                    a = dataclasses.replace(a, start_bar=snapped)
                elif a.start_bar is not None and a.start_bar > orig:
                    a = dataclasses.replace(a, start_bar=a.start_bar + delta)
                elif a.at_bar is not None and a.at_bar > orig:
                    a = dataclasses.replace(a, at_bar=a.at_bar + delta)
                elif a.bar is not None and a.bar > orig:
                    a = dataclasses.replace(a, bar=a.bar + delta)
            elif a.type == "bass_swap" and a.at_bar is not None and orig <= a.at_bar <= orig + 40:
                a = dataclasses.replace(a, at_bar=a.at_bar + delta)
            new_result.append(a)
        result = new_result

    return result
```

Wire it into `normalize()` — it must run **before** `_snap_bass_swap_bars`. Change:

```python
    actions = _enforce_t2_bass_zero(actions)
    actions = _inject_eq_duration(actions)
    actions = _snap_bass_swap_bars(actions)
```

To:

```python
    actions = _enforce_t2_bass_zero(actions)
    actions = _inject_eq_duration(actions)
    actions = _snap_fade_in_anchor(actions)
    actions = _snap_bass_swap_bars(actions)
```

- [ ] **Step 5: Run all normalizer enforcement tests**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/test_normalizer_enforcement.py -v
```

Expected: 9 PASS

- [ ] **Step 6: Run full suite**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -q
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add claude-dj/normalizer.py claude-dj/tests/test_normalizer_enforcement.py
git commit -m "feat: anchor-first phrase snapping, 1-bar loop support in normalizer"
```

---

## Task 3: Executor — verify slip-mode loop behaviour

The executor already implements slip-mode for loops: when a loop completes, `play_from_ms` is rebased to where the track would be had it played through normally. This task writes tests that document and verify that behavior — no code changes expected.

**Files:**
- Create: `claude-dj/tests/test_executor_slip_mode.py`

- [ ] **Step 1: Write the slip-mode verification tests**

```python
# claude-dj/tests/test_executor_slip_mode.py
"""
Verify that loop actions use slip-mode semantics: the track's source position
continues advancing past the loop boundary during the loop. When the loop ends,
source_pos resumes from where the track would have been without the loop.
"""
import pytest
from executor import bars_to_ms, compute_cursors_at_ms
from schema import MixAction, MixScript, MixTrackRef


def _script(actions, n_tracks=1):
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=120.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


def test_loop_source_pos_stays_in_phrase_during_loop():
    """While loop is active, source_pos loops within [loop_start, loop_start+phrase]."""
    bpm = 120.0
    loop_start_bar = 8
    loop_bars = 2
    # Check source_pos mid-second-repeat (1.5 * phrase_ms into the loop)
    phrase_ms = bars_to_ms(loop_bars, bpm)
    loop_start_ms = bars_to_ms(loop_start_bar, bpm)
    target_ms = loop_start_ms + int(phrase_ms * 1.5)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=loop_start_bar,
                  loop_bars=loop_bars, loop_repeats=4),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    # Source position should be loop_start_ms + (1.5 * phrase) % phrase = 0.5 * phrase
    expected_source = loop_start_ms + int(phrase_ms * 0.5)
    assert abs(c.source_pos_ms - expected_source) <= 10  # 10ms tolerance


def test_loop_source_pos_after_loop_ends_is_slip_position():
    """After loop completes, source_pos == where the track would be without the loop."""
    bpm = 120.0
    loop_start_bar = 8
    loop_bars = 2
    loop_repeats = 3
    phrase_ms = bars_to_ms(loop_bars, bpm)
    loop_start_ms = bars_to_ms(loop_start_bar, bpm)
    # Check at loop_end_ms + half a bar
    loop_end_ms = loop_start_ms + phrase_ms * loop_repeats
    target_ms = loop_end_ms + bars_to_ms(1, bpm) // 2

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=loop_start_bar,
                  loop_bars=loop_bars, loop_repeats=loop_repeats),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    # Slip position: loop_start + phrase*repeats + half_bar (as if loop never ran)
    expected = loop_start_ms + phrase_ms * loop_repeats + bars_to_ms(1, bpm) // 2
    assert abs(c.source_pos_ms - expected) <= 10


def test_loop_end_rebases_mix_start():
    """After loop ends, the track's mix_start_ms is rebased to loop_end_ms."""
    bpm = 120.0
    loop_start_ms = bars_to_ms(4, bpm)
    phrase_ms = bars_to_ms(2, bpm)
    loop_end_ms = loop_start_ms + phrase_ms * 2
    # Query one bar after loop end
    target_ms = loop_end_ms + bars_to_ms(1, bpm)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=4, loop_bars=2, loop_repeats=2),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    assert c.loop_start_ms is None  # loop is done
    assert c.mix_start_ms == loop_end_ms


def test_one_bar_loop_works():
    """1-bar loops are valid and cycle within a single bar."""
    bpm = 120.0
    loop_start_ms = bars_to_ms(16, bpm)
    phrase_ms = bars_to_ms(1, bpm)
    # Check mid-loop
    target_ms = loop_start_ms + int(phrase_ms * 2.7)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=16, loop_bars=1, loop_repeats=8),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    expected_source = loop_start_ms + int(phrase_ms * 0.7)
    assert abs(c.source_pos_ms - expected_source) <= 10
```

- [ ] **Step 2: Run the tests**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/test_executor_slip_mode.py -v
```

Expected: 4 PASS — no executor code changes needed (slip-mode was already implemented correctly).

If any test fails, the executor's loop logic has a bug. In that case: read `compute_cursors_at_ms` at lines 374–403 in `executor.py`, fix the rebase logic, and re-run.

- [ ] **Step 3: Commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add claude-dj/tests/test_executor_slip_mode.py
git commit -m "test: verify executor slip-mode loop semantics"
```

---

## Task 4: mix_director — situation summary and zone trim

**Files:**
- Modify: `claude-dj/mix_director.py` (add two helper functions only)

- [ ] **Step 1: Add `_trim_zone` and `_format_situation_summary` to mix_director.py**

Find `_format_zone_table` (around line 757). Add the two new functions directly before it:

```python
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
    # T1 section label at exit bar
    t1_section = "unknown"
    for s in t1.sections:
        if s.start_bar <= window["t1_exit_bar"] < s.end_bar:
            t1_section = s.label.upper()
            break

    t1_bars_remain = max(0, t1.bar_grid.n_bars - window["t1_exit_bar"])

    # T2 intro type from mixing profile
    t2_profile = getattr(t2, "mixing_profile", None)
    intro_type = t2_profile.intro_type if t2_profile else "unknown"

    # First harmonic bar in T2 zone
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
```

- [ ] **Step 2: Verify the functions work in isolation**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -c "
import sys; sys.path.insert(0, '.')
from mix_director import _trim_zone, _format_situation_summary
zone = [{'bar': i, 'drums': 0.5, 'harmonic': 0.1, 'rms': 0.4, 'onsets': 2, 'brightness': 0.3, 'vocals': 0.0, 'tags': []} for i in range(50)]
trimmed = _trim_zone(zone, 16)
print('trimmed len:', len(trimmed))
assert len(trimmed) == 16
print('OK')
"
```

Expected: `trimmed len: 16` then `OK`.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -q
```

Expected: all passing.

- [ ] **Step 4: Commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add claude-dj/mix_director.py
git commit -m "feat: add _format_situation_summary and _trim_zone to mix_director"
```

---

## Task 5: mix_director — rewrite _format_plan_prompt, remove _compute_zone_hints

**Files:**
- Modify: `claude-dj/mix_director.py`

- [ ] **Step 1: Delete `_compute_zone_hints`**

`_compute_zone_hints` spans from line 861 to approximately line 1020 (~160 lines). It is only called from `_format_plan_prompt`. Delete the entire function body (from `def _compute_zone_hints(` through its closing line).

Verify it's gone:

```bash
grep -n "_compute_zone_hints" /Users/DantesFolder/"Claude DJ"/claude-dj/mix_director.py
```

Expected: no output (function deleted and call site not yet updated — that's fine, step 2 removes the call).

- [ ] **Step 2: Rewrite `_format_plan_prompt`**

Replace the entire `_format_plan_prompt` function (from `def _format_plan_prompt(` through its `return (...)`) with:

```python
def _format_plan_prompt(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
    concept: dict | None = None,
) -> str:
    situation = _format_situation_summary(t1, t2, window, t2_zone)

    # Trim zones: T1 exit = 24 bars, T2 entry = 16 bars
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
    if loop_safe_bars:
        loop_rule = (
            f"3. [LOOP_SAFE] bars in T1 exit zone: {loop_safe_bars}. "
            "Consider looping T1 at one of these points (1–2 bars) to stabilize the swap."
        )
    else:
        loop_rule = "3. No [LOOP_SAFE] bars in T1 exit zone — use a straight blend."

    t1_all_high = all(r.get("rms", 1.0) >= 0.5 for r in t1_rows)
    energy_rule = (
        "4. T1 exit zone is uniformly high-energy (all rms ≥ 0.5). "
        "Note this in reasoning — consider starting the transition earlier."
        if t1_all_high else
        "4. Use the lowest-rms bars in T1 exit zone as the transition runway."
    )

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

    return (
        concept_block
        + coord_note
        + situation + "\n\n"
        + t1_table + "\n\n"
        + t2_table + "\n\n"
        + rules + "\n\n"
        + "Output the transition actions as JSON."
    )
```

- [ ] **Step 3: Clear `_PLAN_TASK_SUFFIX`**

Find `_PLAN_TASK_SUFFIX = """` (around line 782). Replace the entire multi-line string with an empty string:

```python
_PLAN_TASK_SUFFIX = ""
```

The system prompt (`dj_skill.md`) is still loaded via `_load_system_prompt()` and provides Claude with action schema reference. The task-specific rules are now inline in the user turn via `_format_plan_prompt`.

- [ ] **Step 4: Verify the prompt looks right**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -c "
import sys; sys.path.insert(0, '.')
from mix_director import _format_plan_prompt
from schema import TrackAnalysis, BarGrid, KeyInfo, StemPaths, MixingProfile, TransitionWindow

t1 = TrackAnalysis(
    id='T1', title='Test Track A', artist='Artist A', file='/t1.mp3',
    duration_s=300.0, bpm=128.0, first_downbeat_s=0.5,
    key=KeyInfo(camelot='8A', standard='Am'),
    energy_overall=7, loudness_dbfs=-10.0,
    bar_grid=BarGrid(n_bars=100, beats_per_bar=4),
    energy_curve_per_bar='5555556677889988776655',
    sections=[], cue_points=[],
    stems=StemPaths(vocals='', drums='', bass='', other=''),
    mixing_profile=MixingProfile(
        vocal_bars=[], loop_candidates=[],
        transition_windows=[TransitionWindow(bar=72, quality=8, character='drums-only')],
        intro_type='drums-only', outro_type='drums-only',
        dj_notes='Clean drums outro from bar 72.',
    ),
)
t2 = TrackAnalysis(
    id='T2', title='Test Track B', artist='Artist B', file='/t2.mp3',
    duration_s=280.0, bpm=128.0, first_downbeat_s=0.3,
    key=KeyInfo(camelot='9A', standard='Dm'),
    energy_overall=6, loudness_dbfs=-11.0,
    bar_grid=BarGrid(n_bars=95, beats_per_bar=4),
    energy_curve_per_bar='4444556677889988776644',
    sections=[], cue_points=[],
    stems=StemPaths(vocals='', drums='', bass='', other=''),
    mixing_profile=None,
)
window = {'t1_exit_bar': 72, 't2_enter_bar': 0, 'window_bars': 16, 'style': 'blend'}
t1_zone = [{'bar': 72+i, 'drums': 0.7, 'harmonic': 0.05, 'rms': 0.42, 'onsets': 2,
             'brightness': 0.3, 'vocals': 0.0, 'tags': ['LOOP_SAFE']} for i in range(24)]
t2_zone = [{'bar': i, 'drums': 0.65, 'harmonic': 0.1, 'rms': 0.38, 'onsets': 3,
             'brightness': 0.35, 'vocals': 0.0, 'tags': ['FADE_IN_OK']} for i in range(16)]

prompt = _format_plan_prompt(t1, t2, t1_zone, t2_zone, window)
print(prompt[:1200])
print('--- length:', len(prompt), 'chars ---')
"
```

Expected: prompt shows SITUATION block, T1 exit zone (24 rows), T2 entry zone (16 rows), RULES with loop and energy rules. No hints block, no examples. Length should be ~2000–3000 chars (vs. current ~6000–8000).

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -q
```

Expected: all passing. Note: `test_derived_hints.py` tests `_compute_zone_hints` — that function is now deleted. Those tests should be deleted too.

- [ ] **Step 6: Delete test_derived_hints.py**

```bash
rm /Users/DantesFolder/"Claude DJ"/claude-dj/tests/test_derived_hints.py
```

Re-run suite:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -q
```

Expected: all remaining tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add claude-dj/mix_director.py claude-dj/tests/test_derived_hints.py
git commit -m "feat: Phase 2 prompt stripped to situation+zone+4rules; remove _compute_zone_hints"
```

---

## Task 6: Integration verification

- [ ] **Step 1: Run the full test suite one final time**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass. Count should be approximately 99 minus the deleted `test_derived_hints.py` tests (typically 17), so ~82+ passing.

- [ ] **Step 2: Smoke-test the normalizer changes with a realistic script**

```bash
cd /Users/DantesFolder/"Claude DJ"/claude-dj
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -c "
import sys; sys.path.insert(0, '.')
from normalizer import normalize
from schema import MixAction, MixScript, MixTrackRef

tracks = [
    MixTrackRef(id='T1', path='/t1.mp3', bpm=128.0, first_downbeat_s=0.0),
    MixTrackRef(id='T2', path='/t2.mp3', bpm=128.0, first_downbeat_s=0.0),
]
# Simulate a typical Claude output with common failures:
#   - T2 fade_in has bass=0.8 (should be forced to 0)
#   - eq missing eq_duration_bars (should get 4 injected)
#   - fade_in at bar 20 (should snap to 16)
#   - bass_swap at bar 28 (should co-shift to 24)
actions = [
    MixAction(type='play', track='T1', at_bar=0, from_bar=0),
    MixAction(type='eq', track='T1', bar=16, low=0.0),
    MixAction(type='fade_in', track='T2', start_bar=20, duration_bars=16, from_bar=0,
              stems={'drums': 0.8, 'bass': 0.8, 'other': 0.6}),
    MixAction(type='bass_swap', track='T1', at_bar=28, incoming_track='T2'),
    MixAction(type='fade_out', track='T1', start_bar=20, duration_bars=16),
    MixAction(type='play', track='T2', at_bar=36, from_bar=16),
]
result = normalize(MixScript(mix_title='test', reasoning='', tracks=tracks, actions=actions))
for a in result.actions:
    print(a)

fi = next(a for a in result.actions if a.type == 'fade_in')
swap = next(a for a in result.actions if a.type == 'bass_swap')
eq_a = next(a for a in result.actions if a.type == 'eq' and a.track == 'T1' and a.low == 0.0)

assert fi.stems['bass'] == 0.0, f'bass not zeroed: {fi.stems}'
assert fi.start_bar % 8 == 0, f'fade_in not phrase-aligned: {fi.start_bar}'
assert swap.at_bar > fi.start_bar, f'bass_swap before fade_in: swap={swap.at_bar} fi={fi.start_bar}'
assert eq_a.eq_duration_bars == 4, f'eq_duration not injected: {eq_a.eq_duration_bars}'
print('All assertions passed.')
"
```

Expected: all assertions pass; printed actions show corrected values.

- [ ] **Step 3: Final commit**

```bash
cd /Users/DantesFolder/"Claude DJ"
git add -A
git commit -m "chore: Phase 2 simplification complete — integration verified"
```

---

## Self-Review

**Spec coverage:**
- § 3 (Phase 2 prompt) → Task 5 Step 2 (`_format_plan_prompt` rewrite) ✓
- § 4.1 (anchor-first ×8 snapping) → Task 2 Step 4 (`_snap_fade_in_anchor`) ✓
- § 4.2 (T2 bass=0 enforcement) → Task 1 Step 3 (`_enforce_t2_bass_zero`) ✓
- § 4.3 (EQ duration injection) → Task 1 Step 3 (`_inject_eq_duration`) ✓
- § 4.4 (bass swap presence) → already in existing `_inject_bass_swap_if_missing`, no change needed ✓
- § 5 (slip-mode loop semantics) → Task 3 verifies existing behaviour is already correct ✓
- § 6 (_format_situation_summary computed fields) → Task 4 Step 1 ✓
- § 7 (files changed table) → all listed files addressed ✓
- § 3 "What is removed" → `_compute_zone_hints()` deleted Task 5 Step 1; examples removed Task 5 Step 2; PLAN_TASK_SUFFIX cleared Task 5 Step 3; profile injection removed (it was already only in Phase 1) ✓
- 1-bar loop support → Task 2 Step 3 (`_VALID_LOOP_BARS` and `_snap_loop_bars`) ✓

**No placeholders found.**

**Type consistency:** All references to `_format_situation_summary`, `_trim_zone`, `_snap_fade_in_anchor`, `_enforce_t2_bass_zero`, `_inject_eq_duration` are consistent across tasks.
