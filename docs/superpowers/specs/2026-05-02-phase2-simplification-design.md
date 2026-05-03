# Phase 2 Simplification — Design Spec

**Status:** Approved for implementation  
**Date:** 2026-05-02

---

## 1. Problem

The current Phase 2 (transition planning) produces poor output despite accurate zone data. Root causes confirmed by research:

- **Information overload:** The prompt contains a 48-bar zone table, a hints block (VOCAL SITUATION, bass_swap BECAUSE, LOOP CANDIDATES, RECOMMENDED TECHNIQUE), mixing profile injection, 3 retrieved examples, and a full skill doc reference. The "Lost in the Middle" (TACL 2024) and anchoring bias (arxiv:2412.06593) papers confirm models drop buried constraints and anchor to the most salient structural features — here, the "default = 16 bars" line in the examples.
- **Wrong examples:** Retrieved examples are biased toward same-key/same-BPM easy cases. The Few-shot Dilemma paper (arxiv:2509.13196) documents that mismatched examples actively hurt by signaling the wrong output distribution. Zero-shot outperforms bad-shot.
- **Prompt-only enforcement fails:** The rule "always use eq_duration_bars: 4" exists in the prompt but is ignored in every logged run. Constrained-decoding research confirms prompt enforcement tops out at ~85% reliability for numeric formatting rules. Post-processing is strictly more reliable.
- **Hints block over-anchors:** The `_compute_zone_hints()` derived hints give Claude a confident wrong recommendation when T1's exit zone is all high-energy (the "lowest in zone" bass swap bar may be at d+h=1.91). Claude follows the hint without questioning it.

---

## 2. Approach

**Strip Phase 2 to the minimum Claude actually needs to reason well. Move enforcement from prompt to normalizer.**

Three changes:

1. **Phase 2 prompt:** Four-part structure — situation summary, T1 exit zone (~24 bars), T2 entry zone (~16 bars), four rules. No hints block. No examples. No profile injection.
2. **Normalizer:** Enforce the four hard rules in code after Claude responds. Snap anchor events to ×8, then recompute dependent bars as offsets. Never snap bars independently.
3. **Executor:** Add slip-mode loop semantics so T1's playhead continues internally past the loop boundary — releasing the loop picks up from where T1 would have been naturally.

Phase 0 and Phase 1 are unchanged.

---

## 3. Phase 2 Prompt (new)

```
SITUATION:
  T1: "[Title]" by [Artist] — exits [SECTION] around bar X. [N] bars of track remain.
  T2: "[Title]" by [Artist] — [intro_type] intro. First harmonic content: bar [N].
  Key: [T1_camelot]→[T2_camelot] (Camelot dist=[N]). BPM delta: [Z].

T1 EXIT ZONE (bars X–Y):
  b 80: d=0.72 h=0.04 r=0.41 on=2  [LOOP_SAFE]
  b 88: d=0.68 h=0.07 r=0.39 on=2  [LOOP_SAFE]
  ...

T2 ENTRY ZONE (bars 0–16):
  b  0: d=0.65 h=0.12 r=0.38 on=3  [FADE_IN_OK]
  ...

RULES:
1. Never have two bass-active tracks simultaneously. T2 enters with bass=0.0.
   Bass swap happens ≥8 bars after T2 enters, at the lowest-energy bar in zone.
2. All EQ moves must include eq_duration_bars (default: 4). No snap cuts.
3. If [LOOP_SAFE] bars exist above, consider looping T1 at that point
   (1–2 bars) to stabilize the swap window.
4. If T1 exit zone shows no bars below r=0.5, note this in reasoning and
   start the transition earlier than the suggested window.

Output transition actions as JSON.
```

**What is removed from Phase 2:**
- `_compute_zone_hints()` output (VOCAL SITUATION, bass_swap BECAUSE, LOOP CANDIDATES, RECOMMENDED TECHNIQUE blocks)
- Retrieved examples from examples bank
- Mixing profile injection (stays in Phase 1 only)
- `_PLAN_TASK_SUFFIX` rules list (replaced by the four rules above)
- Full skill doc reference

**Zone table:** Shrink T1 exit zone from 48 bars to 24 bars (12 bars before suggested exit + 12 bars after). T2 entry zone: 16 bars. Total: ~40 rows.

---

## 4. Normalizer — New Enforcement Rules

All four rules enforced post-Claude, regardless of what the model output:

### 4.1 Anchor snapping (×8 phrase alignment)

Identify the anchor event: the `fade_in(T2)` `at_bar` value. Snap it to the nearest multiple of 8. Then recompute all other action bars as offsets from that anchor — do not snap them independently.

Example: Claude outputs `fade_in(T2, at_bar=17)`, `bass_swap(at_bar=25)`. Snap anchor 17→16. bass_swap was 8 bars after anchor → becomes 16+8=24.

Snap only: `fade_in` start, `fade_out` start, `bass_swap` at_bar, `play` at_bar. Do not snap: `eq_duration_bars`, `loop` lengths (those are relative durations, not phrase anchors).

### 4.2 T2 bass=0 enforcement

If T2's first `fade_in` action has `bass > 0.0`, set `bass=0.0`. Non-negotiable.

### 4.3 EQ duration injection

If any `eq` action is missing `eq_duration_bars`, inject `eq_duration_bars=4`. Apply to all eq actions in the script.

### 4.4 Bass swap presence

If no bass swap is present (no action that sets T1 `low=0` and T2 `low=1.0` within the transition window), inject one at anchor + 8 bars with `eq_duration_bars=4`.

---

## 5. Loop Slip-Mode Semantics

The loop-as-stabilizer technique requires slip-mode behavior:

- When a `loop` action fires on T1, T1's internal playhead continues past the loop boundary while the loop plays.
- When the loop is released (either by a `loop_off` action or when T1's `fade_out` fires), T1 resumes from its internal playhead position — not from the loop start.
- This prevents a jarring reset artifact when the loop ends.

**Loop lengths for stabilization:** 1–2 bars. The normalizer snaps loop lengths to the nearest valid value in `_VALID_LOOP_BARS = (1, 2, 4, 8, 16)`. Sub-bar loops (0.5, 0.25) are not used for stabilization — those are effects territory.

**Trigger condition (in prompt):** Loop is offered when `[LOOP_SAFE]` bars appear in T1 exit zone. Claude decides whether to use it; it is not injected by the normalizer.

---

## 6. Situation Summary — Computed Fields

`_format_situation_summary(t1, t2, window)` produces the SITUATION block. Computed fields:

| Field | Source |
|---|---|
| `[SECTION]` | Section label from `t1.sections` at `window["t1_exit_bar"]` |
| `[N] bars of track remain` | `t1.bar_grid.n_bars - window["t1_exit_bar"]` |
| `[intro_type]` | `t2.mixing_profile.intro_type` if present, else "unknown" |
| `First harmonic content: bar [N]` | First T2 zone bar where `h > 0.20`, or "unknown" |
| `Camelot dist` | `_camelot_distance(t1.key.camelot, t2.key.camelot)` |
| `BPM delta` | `abs(t1.bpm - t2.bpm)` rounded to 1 decimal |

---

## 7. Files Changed

| File | Change |
|---|---|
| `claude-dj/mix_director.py` | Replace `_format_plan_prompt()`: remove hints call, remove examples, add `_format_situation_summary()`; shrink zone table to 24+16 bars; replace `_PLAN_TASK_SUFFIX` with inline 4-rule block |
| `claude-dj/mix_director.py` | Remove `_compute_zone_hints()` entirely |
| `claude-dj/normalizer.py` | Add anchor-first ×8 snapping, T2 bass=0 enforcement, eq_duration injection, bass swap presence check |
| `claude-dj/executor.py` | Add slip-mode semantics for loop actions: track internal playhead separately from loop playback position |
| `claude-dj/tests/test_normalizer_enforcement.py` | New: tests for all four normalizer rules |
| `claude-dj/tests/test_executor_slip_mode.py` | New: tests for slip-mode loop behavior |

`analyze.py`, `schema.py`, `cli.py`, `server.py`, `dj_session.py` — **unchanged**.

---

## 8. Out of Scope

- Changes to Phase 0 or Phase 1
- Filter sweep action type (HPF sweep — future feature)
- Anti-pattern examples in the examples bank (future — once fundamentals are stable)
- Vocal detection via stems (separate issue — requires Demucs in dj_session.py)
- Cross-genre or high-BPM-delta transitions
