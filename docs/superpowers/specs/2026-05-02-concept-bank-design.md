# Concept Bank + Skill File Trim — Design Spec
**Date:** 2026-05-02  
**Status:** Approved for implementation

---

## 1. Problem

Two related failures:

1. **dj_skill.md has grown to 1022 lines.** Every debug pass added rules. The file now mixes per-transition mechanics (what the executor does) with set-level creative direction (energy arcs, genre philosophy, default overlap lengths). The combined weight creates contradictions, noise, and worse mixes as it grows.

2. **Claude has no set-level creative intent.** It plans transitions in isolation — it knows the zone data, the key relationship, the BPM — but it has no idea what *kind* of set this is. A sunrise set and a peak-time set use completely different techniques, but Claude defaults to the same generic blend pattern every time.

---

## 2. Architecture

Clean split of concerns:

```
dj_skill.md           → mechanics only (~300 lines)
                         What every transition must do regardless of context.
                         Sections: critical rules, harmonic moves, bass swap
                         protocol, transition checklist, loop rules, action reference.

concept_bank/*.json   → creative direction (one file per set archetype)
                         What this set should feel like.
                         Carries: energy intent, overlap target, technique bias,
                         EQ patterns, stem weights, and a full technique walkthrough
                         Claude can directly translate into actions.
```

The skill file becomes the **engine spec**. The concept file becomes the **director's intent**. Claude gets both — but they're clearly separated, no rule bleed.

---

## 3. dj_skill.md Trim

### What gets cut

| Section | Lines | Reason for removal |
|---|---|---|
| §2 Genre profiles | ~80 | Track analysis already encodes BPM/structure. Claude doesn't need to memorize "deep house = 118–125 BPM" when the track says so. |
| §4 + §12 Energy arc management | ~80 | This is exactly what the concept bank covers. Must not be in the base skill. |
| §10 Frequency precision reference | ~60 | Frequency tables and commentary. Keep the band map (4 lines), cut the rest. |
| §11 Cue point strategy | ~40 | Handled by the analyzer. Not needed in the prompt. |
| §13 Genre-specific transition templates | ~60 | Move to concept bank. |
| Prose explanations throughout | ~150 | Sections 1, 3, 7, 14 all contain multi-paragraph "why" blocks. Cut to rule + constraint only. |

### What stays (tightened)

| Section | Keep |
|---|---|
| §0 Critical rules | All 10 rules, tightened to one line each |
| §1 Harmonic mixing | Camelot ruleset table + distance penalty. Cut prose explanations. |
| §3.1–3.5 Transition techniques | Bass swap protocol, double-drop rules, damage limitation. Cut verbose commentary. |
| §6 Operational checklist | All 10 steps — this is the most load-bearing section |
| §7 Loop technique | Rules + zone triggers. Cut genre-by-genre table. |
| §14 Action reference | Schema + zone triggers for each action type. Cut multi-paragraph variant descriptions. |

### `_TASK_PROMPT` and `_PLAN_TASK_SUFFIX` in mix_director.py

After the skill file trim, audit both constants for:
- Content that duplicates trimmed skill file sections → remove
- The bass swap pattern block → keep (it's a concrete action sequence, not philosophy)
- The OUTPUT SCHEMA block → keep
- The FADE_OUT IS MANDATORY block → keep
- Zone annotation legend in `_PLAN_TASK_SUFFIX` → keep

---

## 4. Concept Bank Schema

File location: `claude-dj/concept_bank/<slug>.json`

```json
{
  "name": "sunrise",
  "display_name": "Sunrise Set",
  "description": "Patient hypnotic build from near-silence to full energy.",
  "prompt_injection": "...",
  "directives": {
    "preferred_overlap_bars": 32,
    "preferred_technique": "blend",
    "avoid_technique": ["cut", "drop_swap"],
    "bass_swap_placement": "late"
  },
  "example_ids": ["ex_003.json", "ex_007.json"]
}
```

### Field definitions

| Field | Type | Purpose |
|---|---|---|
| `name` | string | Slug — used for CLI `--concept <name>` and file loading |
| `display_name` | string | Human-readable label, logged at mix start |
| `description` | string | One-line summary. No code hook. |
| `prompt_injection` | string | **Primary mechanism.** Full technique walkthrough prepended to Phase 2 planning prompt. Must map DJ technique to specific actions with EQ values, stem weights, and bar offsets. |
| `directives.preferred_overlap_bars` | int | Biases Phase 1 window selection. Soft preference, not a hard floor. |
| `directives.preferred_technique` | string | `"blend"`, `"cut"`, or `"drop_swap"` — biases Phase 1 style selection |
| `directives.avoid_technique` | string[] | Phase 1 prompt explicitly lists these as discouraged |
| `directives.bass_swap_placement` | string | `"early"` (~25%), `"mid"` (50%), `"late"` (~75%) into overlap window |
| `example_ids` | string[] | RAG score bonus: `−0.8` for examples in this list when concept is active |

### Dropped from original spec (YAGNI)

- `energy_arc_shape` — no track ordering logic yet
- `transition_arc_template` — folds into `prompt_injection` prose
- `fade_in_stem_philosophy` — folds into `prompt_injection`
- `eq_philosophy` — folds into `prompt_injection`
- `target_bpm_range` / `target_genres` — no code hooks, not worth schema weight

### System constraint: 2-bar loops

The normalizer currently enforces `loop_bars` minimum of 4. Several concepts (especially `tension_build`, `peak_time`, `hypnotic`) use 2-bar loops that are standard in tech house. **The normalizer must be updated to allow `loop_bars: 2`** as part of this implementation.

### System constraint: filter sweep approximation

Concepts reference "HPF sweep" and "filter sweep" techniques (gradual frequency dissolve). The executor has no `filter_sweep` action. These are approximated as a sequence of stepped `eq()` calls: high cut first, then mid, then low. The `prompt_injection` for affected concepts explicitly describes this pattern using `eq()` actions so Claude produces valid output.

---

## 5. The 10 Concepts

---

### `warmup`
**Arc:** Ramp 2→7. Patient build, never peak early.  
**Overlap:** 32 bars  
**Technique:** Blend with drums-first stem order  
**Bass swap:** Mid  

```
prompt_injection:

WARMUP SET. Your job is to invite the crowd in, not impress them. Energy starts low and 
climbs in small steps. Never play your best transition technique here — save it.

BLEND SEQUENCE (every transition):
1. T2 enters with: fade_in stems={drums:0.7, other:0.2, bass:0.0}. Drums and distant 
   atmosphere only. No bass, no lead elements yet.
2. Hold T2 in this state for at least 16 bars. Let the groove layer before anything else 
   enters.
3. At bar +8: eq(T1, low=0.6) — gentle low reduction, not a hard cut. Preserve warmth.
4. At bar +16: raise T2 other to 0.4 — pads and atmosphere start to bleed through.
5. bass_swap at bar +16 (midpoint of a 32-bar window). eq(T1, low=0.0). eq(T2, low=1.0).
6. eq(T1, mid=0.6) at bar +20 — ease T1 mids back to let T2 melody breathe.
7. T1 fades out over the back half of the window. No loops needed unless T1 outro is 
   under 16 bars clean.

OVERLAP: 32 bars minimum. Use loop(T1, loop_bars=8, loop_repeats=2) if T1 has fewer 
than 24 bars of clean outro.

FORBIDDEN: drop_swap, cut, window_bars < 24, any overlap where T2 full-mix enters 
before T1 is at low volume. Never play a track that is higher energy than the current 
track. Each T2 must be equal or +1 energy only.
```

---

### `sunrise`
**Arc:** Slow flat build 2→6. Maximum patience.  
**Overlap:** 32 bars minimum  
**Technique:** Cross-deck loop swap  
**Bass swap:** Late (75%)  

```
prompt_injection:

SUNRISE SET. The goal is transitions the crowd never notices. Music just changes. 
Use maximum patience — 32 bars is the minimum, not the target.

CROSS-DECK LOOP SWAP SEQUENCE:
1. Find a clean 2-bar or 4-bar drum loop in T2 (drums only, h < 0.1 in zone data). 
   Start it running: loop(T2, loop_bars=4, loop_repeats=4). T2 enters as repeating 
   drum texture layered over T1. This is not a fade yet.
2. fade_in(T2, duration_bars=32, from_bar=<first drum bar>, stems={drums:0.7, other:0.1, 
   bass:0.0}). T2 sounds like distant percussion added to T1. Hold 'other' at 0.1 
   for the first 16 bars.
3. At bar +8: eq(T1, low=0.5) — gentle low reduction. Not a hard kill. Preserves warmth. 
   This is not the bass swap.
4. At bar +16: raise T2 other to 0.3. Atmosphere starts to bleed in underneath T1.
5. At bar +24 (75% through the 32-bar window): bass_swap(T1, incoming_track=T2). 
   eq(T1, low=0.0) hard kill. eq(T2, low=1.0) restore. The bass is heard as T1 
   releasing, not T2 arriving — because T2 has been in the mix for 24 bars already.
6. loop(T1, start_bar=<last clean drum phrase>, loop_bars=4, loop_repeats=2). T1 
   loops into its final drum texture.
7. Break T2 loop — play(T2, at_bar=<loop_end>, from_bar=<loop_end offset>). T2 plays 
   freely while T1 loops down.
8. fade_out(T1, start_bar=<loop_end>, duration_bars=8). T1 loop dissolves.

STEM WEIGHTS DURING FADE: drums:0.7 for full 32 bars. other: 0.1 → 0.3 (open at bar 16). 
bass: 0.0 until step 5. Never open vocals unless T1 has been silent for 8+ bars.

OVERLAP: 32 bars absolute minimum. 24 bars only if T1 has no clean material left.
FORBIDDEN: window_bars < 24, bass_swap before 60% of window, cut, drop_swap, opening 
T2 bass before step 5, any transition that creates a perceivable "moment of change".
```

---

### `hypnotic`
**Arc:** Low sustained plateau 5→6. Texture shifts, not energy shifts.  
**Overlap:** 32–64 bars  
**Technique:** Long textural blend, binary kick swap  
**Bass swap:** Late  

```
prompt_injection:

HYPNOTIC SET. Techno discipline. Transitions are textural, not structural. The kick 
never stops — it just changes character. Energy stays in a narrow band. The crowd is 
in a trance state; sudden changes break the hypnosis.

TEXTURAL BLEND SEQUENCE:
1. T2 enters underneath T1's ongoing groove: fade_in(T2, duration_bars=32, 
   stems={drums:0.0, other:0.8, bass:0.0}). T2's atmospherics, synth textures, and 
   pads layer in while T1's kick continues. Drums on T2 are MUTED — the crowd follows 
   T1's kick only.
2. At bar +8: eq(T1, mid=0.7) — T1 mids pull back slightly. T2 textures emerge into 
   the space created.
3. At bar +16: open T2 drums — update stems to drums:0.6 (or use eq(T2, high=0.8) 
   to bring hats in first). T2's hi-hats layer over T1's kick.
4. At bar +24: binary kick swap. bass_swap(T1, incoming_track=T2). eq(T1, low=0.0). 
   eq(T2, low=1.0). This is instantaneous — one kick or the other, never both. 
   The crossfader swap is the only abrupt move in this entire transition.
5. eq(T1, mid=0.3) immediately after kick swap. T1 textures pull fully back.
6. T1 fades out over the back 16 bars. T2's atmospherics are already fully established 
   — the crowd doesn't register the change.

OVERLAP: 32 bars minimum. 48–64 bars preferred for maximum invisibility. Techno tracks 
are designed for this — use the full outro.

LOOP USAGE: Loops are encouraged to extend short outros. loop(T1, loop_bars=4, 
loop_repeats=2) on any clean percussion-only phrase near T1's outro.

FORBIDDEN: drop_swap, cuts, window_bars < 24, opening T2 kick before step 3, 
two kicks playing simultaneously at any point, energy jumps > +1 between tracks.
Never rush. A transition over 64 bars that the crowd doesn't notice is better than 
a 16-bar transition they do.
```

---

### `peak_time`
**Arc:** Plateau 8→10. Sustained high energy with micro-variation.  
**Overlap:** 16 bars (8 for drop swaps)  
**Technique:** Loop-and-build dominant  
**Bass swap:** Early-to-mid  

```
prompt_injection:

PEAK TIME SET. The loop-and-build is your primary weapon. Use it before every 
significant track introduction. The crowd is at maximum energy — your job is to 
sustain it with variety, not volume.

LOOP-AND-BUILD SEQUENCE (use before dropping T2):
1. Find T1's most driving 8-bar section (high drums, high RMS, active kick — look 
   for zone rows with d > 0.7, r > 0.6). Set loop(T1, loop_bars=8, loop_repeats=2).
2. During the loop: eq(T1, mid=0.6) — T1 mids start pulling back over the 2 repeats. 
   The crowd feels the loop tightening, anticipating a change.
3. On the loop's final repeat: fade_in(T2, start_bar=<loop_bar+8>, duration_bars=8, 
   stems={drums:1.0, bass:0.0, other:0.6}). T2 explodes in over the last loop repeat 
   — full drums, no bass yet.
4. bass_swap at bar +4 of the 8-bar fade (50% — early for peak energy). eq(T1, low=0.0). 
   eq(T2, low=1.0). Energy must not dip.
5. play(T2) at fade_in end. Kill T1 immediately — no lingering fade.

DROP-TO-DROP SEQUENCE (when both tracks have matching drops):
1. fade_in(T2, duration_bars=8, stems={drums:1.0, bass:0.0, other:0.8}). Full energy 
   entry, no bass.
2. bass_swap at bar +4. Instantaneous.
3. eq(T1, mid=0.3) at bass_swap bar. T1 mids drop fast.
4. T1 fade_out over 8 bars simultaneous with T2 fade_in.

OVERLAP: 16 bars standard. 8 bars for drop swaps. Never 32+ bars — that's warmup pacing.

MICRO-VARIATION RULE: Do not use loop-and-build on consecutive transitions. After a 
loop-and-build, the next must be a straight 16-bar blend or drop swap. Vary or the 
technique loses impact.

FORBIDDEN: 32-bar blends, patient stem buildup, bass_swap after 60% of window.
```

---

### `tension_build`
**Arc:** Escalating pressure to a held peak.  
**Overlap:** 16 bars (building to 24 later in set)  
**Technique:** Cross-deck loop swap with rising filter pressure  
**Bass swap:** Late  

```
prompt_injection:

TENSION BUILD SET. Build pressure track by track. Withhold the release. The crowd 
should feel something coming but not know when it lands.

CROSS-DECK LOOP + FILTER PRESSURE SEQUENCE:
1. Start a short loop on T2 before the transition begins: loop(T2, loop_bars=2, 
   loop_repeats=4). T2 runs as a repeating 2-bar drum texture underneath T1.
2. fade_in(T2, duration_bars=16, stems={drums:0.8, other:0.2, bass:0.0}). T2 feels 
   like added percussion pressure on top of T1.
3. Progressive EQ pressure on T1 — step these across 8 bars:
   bar +4:  eq(T1, high=0.7)         — hats start pulling back
   bar +8:  eq(T1, high=0.4, mid=0.8) — T1 losing presence
   bar +12: eq(T1, mid=0.5, low=0.7)  — T1 dissolving in all bands
   This is the HPF sweep equivalent — T1 frequencies disappear in order: highs, 
   mids, lows.
4. bass_swap(T1, incoming_track=T2) at bar +12 (75% through). eq(T1, low=0.0). 
   eq(T2, low=1.0). T2 bass lands as T1 is already dissolving.
5. loop(T1, start_bar=<current phrase>, loop_bars=4, loop_repeats=2). T1 enters a 
   short loop while T2 plays freely — T1 is now trapped/rhythmic.
6. Break T2 loop (if T2 was looping). play(T2 full mix). T2 breaks free.
7. fade_out(T1, start_bar=<loop resume point>, duration_bars=8). T1 loop dissolves.

ENERGY RULE: Each successive track should be +1 energy. Do not plateau. Pressure 
must keep building until the set's peak track.

FORBIDDEN: Long patient blends (> 24 bars), bass_swap before bar +10, opening T2 
fully before T1 is under pressure from EQ steps.
```

---

### `journey`
**Arc:** Classic 3→10→3. Full narrative arc.  
**Overlap:** Varies by set phase  
**Technique:** All techniques — varies deliberately  
**Bass swap:** Varies  

```
prompt_injection:

JOURNEY SET. This is the full narrative arc: warmup → build → peak → release → close. 
You have permission to use every technique in the toolkit. The key is using the RIGHT 
technique for the current phase of the arc.

READ THE ENERGY LEVEL to determine which technique to use:

ENERGY 3–5 (early set, warmup phase):
  → Use warmup blend: 32-bar overlap, stems={drums:0.7, other:0.2, bass:0.0}, 
    bass_swap at midpoint, gentle eq(T1, low=0.5) pre-cut.

ENERGY 5–7 (build phase):
  → Use standard blend with loop extension: 24-bar overlap, stems={drums:0.8, 
    other:0.4, bass:0.0}. Loop T1 if outro is short. Bass_swap at midpoint.

ENERGY 7–9 (peak approach):
  → Use loop-and-build: loop(T1, loop_bars=8, loop_repeats=2), then 16-bar 
    fade_in with drums:1.0. Bass_swap early (bar +4 of 8).

ENERGY 9–10 (peak):
  → Use drop-to-drop or loop-and-build. 8–16 bar overlaps. Full energy entry. 
    No patient stem buildup.

ENERGY DESCENDING (release phase):
  → Filter sweep dissolve: stepped eq(T1, high→mid→low) over 16 bars while 
    T2 fades in as atmosphere. Bass_swap at midpoint. No loops.

ENERGY 3–4 (close):
  → Echo-out simulation: eq(T1, high=0.3, mid=0.4) — thin T1 to its echo tail. 
    T2 enters at low volume as T1 dissolves. 24-bar overlap, gentle.

NEVER use the same technique twice in a row. The journey's power is variety — 
the crowd should not be able to predict what the next transition sounds like.
```

---

### `cool_down`
**Arc:** Descent 8→3. Graceful energy release.  
**Overlap:** 24–32 bars  
**Technique:** Filter sweep dissolve + echo-out simulation  
**Bass swap:** Mid  

```
prompt_injection:

COOL DOWN SET. Each transition must feel like a slight release of pressure. The crowd 
should feel the night winding down without noticing the energy dropping. Never drop a 
banger. Never introduce a track higher energy than the current one.

PRIMARY TECHNIQUE — FILTER SWEEP DISSOLVE:
The outgoing track dissolves by frequency — highs vanish first, then mids, then lows. 
T2 enters from the other direction. Model this with stepped eq() calls:

Step 1 (bar -8 before T2 enters):
  eq(T1, high=0.7) — T1 loses shimmer and air

Step 2 (bar 0, T2 fade_in starts):
  fade_in(T2, duration_bars=24, stems={drums:0.5, other:0.6, bass:0.0})
  eq(T1, high=0.4, mid=0.8) — T1 loses presence

Step 3 (bar +8):
  eq(T1, mid=0.5, low=0.7) — T1 becomes bass-dominant, no melody

Step 4 (bass_swap at bar +12):
  bass_swap(T1, incoming_track=T2). eq(T1, low=0.0). eq(T2, low=1.0).
  T1 goes silent on all bands simultaneously with bass swap.

Step 5 (bar +16 onward):
  T2 opens fully. eq(T2, mid=1.0, high=1.0). T2 at unity.
  T1 fade_out completes. Silence from T1.

SECONDARY TECHNIQUE — ECHO-OUT SIMULATION (use at major section transitions):
When you want a more dramatic section end, simulate an echo tail:
  eq(T1, high=0.2, mid=0.3) — T1 thins to near-nothing
  T2 begins underneath at low volume: fade_in stems={drums:0.4, other:0.5, bass:0.0}
  T2 builds from near-silence over 16 bars while T1's thin signal decays.

OVERLAP: 24–32 bars. Never under 16.
ENERGY: every T2 must be ≤ T1 energy. +1 energy is a mistake in this concept.
FORBIDDEN: loop-and-build (peak technique), drop_swap, cuts without preceding 
filter dissolve, opening T2 at full energy while T1 is still audible.
```

---

### `afterhours`
**Arc:** Low sustained plateau 3→5. Hypnotic repetition, minimal interference.  
**Overlap:** 32+ bars  
**Technique:** Cross-deck loop swap, heavy loop usage  
**Bass swap:** Late  

```
prompt_injection:

AFTERHOURS SET. 4am philosophy. The crowd is deep in the music, not dancing to peaks. 
Transitions must be invisible. Long tracks, long blends, heavy loop usage. Never 
introduce energy — sustain a trance.

FULL CROSS-DECK LOOP SWAP SEQUENCE:
1. Well before the transition, start a loop on T2: loop(T2, loop_bars=4, loop_repeats=6). 
   T2 runs as a long repeating texture underneath T1. Let it run for 16+ bars before 
   any fading begins.
2. fade_in(T2, duration_bars=32, stems={drums:0.6, other:0.3, bass:0.0}). Extremely 
   slow entry. T2 sounds like a layer added to T1, not a new track.
3. At bar +8: eq(T1, low=0.5). Gentle. Preserve warmth.
4. At bar +16: eq(T1, mid=0.7). T1 begins to recede slightly.
5. At bar +24 (75% through): bass_swap(T1, incoming_track=T2). eq(T1, low=0.0). 
   eq(T2, low=1.0). Late swap — T2 has been present for 24 bars, the bass landing 
   feels like T1 leaving, not T2 arriving.
6. loop(T1, start_bar=<last clean drum phrase>, loop_bars=4, loop_repeats=3). 
   T1 enters a repeating drum texture.
7. Break T2 loop. play(T2, full mix). T2 plays freely.
8. fade_out(T1, duration_bars=16). T1 loop dissolves very slowly.

LOOP PHILOSOPHY: Loops are not a technique here — they're the texture. Using a loop 
is not cheating; it's the sound of afterhours. loop_bars=2 or 4, loop_repeats=3–6.

OVERLAP: 32 bars minimum. 48 bars if tracks permit.
ENERGY: Flat. Each T2 should be same energy as T1 — no building, no releasing. 
Variation comes from texture (darker/lighter, sparser/denser), never from energy level.
FORBIDDEN: drop_swap, loop-and-build (too dramatic), energy jumps of any kind, 
window_bars < 24, bass_swap before 60% of window, cuts.
```

---

### `build`
**Arc:** Rising 3→8, no cooldown. Escalating only.  
**Overlap:** 24 bars (tightening to 16 as energy climbs)  
**Technique:** Blend tightening progressively  
**Bass swap:** Mid, moving to early as energy climbs  

```
prompt_injection:

BUILD SET. Energy only goes up. You are handing off to a headliner — leave the room 
at 80% energy, not at peak. Discipline: the temptation is to jump to your big tracks 
early. Do not. Each transition is a small step up.

BLEND TIGHTENING RULE — adjust overlap length to current energy level:
  Energy 3–5: overlap 24 bars, stems={drums:0.7, other:0.3, bass:0.0}, bass_swap mid
  Energy 5–6: overlap 20 bars, stems={drums:0.8, other:0.4, bass:0.0}, bass_swap mid
  Energy 6–7: overlap 16 bars, stems={drums:0.9, other:0.5, bass:0.0}, bass_swap early
  Energy 7–8: overlap 16 bars, loop-and-build optional, bass_swap early

As energy climbs, transitions get tighter and T2 enters with more presence from bar 1.

STANDARD BLEND (energy 3–5):
1. fade_in(T2, duration_bars=24, stems={drums:0.7, other:0.3, bass:0.0})
2. eq(T1, low=0.6) at bar +8.
3. bass_swap at bar +12. eq(T1, low=0.0). eq(T2, low=1.0).
4. eq(T1, mid=0.6) at bar +16. T1 recedes.
5. T1 fade_out starts at bar +12 over 16 bars.

TIGHTENED BLEND (energy 6–8):
1. fade_in(T2, duration_bars=16, stems={drums:1.0, other:0.6, bass:0.0})
2. eq(T1, low=0.0) at bar -4 before T2 enters (aggressive pre-cut).
3. bass_swap at bar +4 (early). eq(T2, low=1.0).
4. eq(T1, mid=0.3) immediately. T1 mids cut fast.
5. T1 fade_out over 16 bars simultaneous with T2 fade_in.

CEILING RULE: Never play a track that is +2 energy above the current track. 
Steps of +1 only. If no +1 track is available, hold energy flat rather than jumping.
FORBIDDEN: energy drops of any kind, cool-down technique, 32-bar blends after 
energy passes 6, bass_swap after 60% of window once energy exceeds 6.
```

---

### `rollercoaster`
**Arc:** Deliberate wave — peaks and valleys.  
**Overlap:** Varies; cuts permitted at valleys  
**Technique:** Full toolkit including bold cuts  
**Bass swap:** Varies  

```
prompt_injection:

ROLLERCOASTER SET. Deliberate contrast. You are allowed to drop energy sharply — that 
is the point. A well-placed energy valley makes the next peak hit harder. Use every 
technique in the toolkit, including cuts.

ENERGY PEAK TRANSITIONS (energy 7–10):
  → Loop-and-build: loop(T1, loop_bars=8, loop_repeats=2), then 16-bar fade_in with 
    drums:1.0, bass_swap at bar +4. High presence, fast handover.

ENERGY VALLEY TRANSITIONS (deliberate energy drop):
  → Bold cut: fade_out(T1, duration_bars=4) — quick fade, not a blend.
    play(T2, at_bar=<exit+4>, from_bar=<T2 mix_in>). T2 enters at low energy 
    immediately. The contrast is intentional. No stems, no fade_in — T2 arrives.
  → Or filter dissolve: stepped eq(T1, high→mid→low) over 8 bars, then T2 enters 
    as atmosphere from near silence.

REBUILD TRANSITIONS (valley → rising back up):
  → Standard 24-bar blend from low energy: stems={drums:0.7, other:0.3, bass:0.0}. 
    Let T2 establish its groove fully before the bass swap.

READING THE ENERGY:
  Rising (T2 energy > T1): tighten overlap, early bass_swap, higher stem openings
  Falling (T2 energy < T1): use cut or filter dissolve, no loop-and-build
  Holding flat: standard blend, mid bass_swap

MACRO RULE: Never drop energy more than 2 levels without a track specifically chosen 
to bridge the gap. The valley should feel intentional, not like a mistake.
FORBIDDEN: using the same technique on more than 2 consecutive transitions. 
Three identical blends in a row is warmup behavior, not rollercoaster.
```

---

## 6. Integration into mix_director.py

### New utility function

```python
def load_concept(slug: str) -> dict | None:
    """Load a concept from concept_bank/<slug>.json. Returns None if not found."""
    path = Path(__file__).parent / "concept_bank" / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
```

### Phase 1 — select_transition_window

Append concept hint to `_WINDOW_PROMPT_TEMPLATE` when concept is loaded:

```
ACTIVE CONCEPT: {concept_display_name}
Prefer: overlap={preferred_overlap_bars} bars, style={preferred_technique}
Avoid: {avoid_technique}
```

### Phase 2 — _format_plan_prompt

Prepend concept block before track summaries:

```python
concept_block = ""
if concept:
    directives = concept.get("directives", {})
    concept_block = (
        f"=== ACTIVE CONCEPT: {concept['display_name'].upper()} ===\n"
        f"{concept['prompt_injection']}\n"
        f"DIRECTIVES: overlap={directives.get('preferred_overlap_bars')} bars | "
        f"technique={directives.get('preferred_technique')} | "
        f"bass_swap={directives.get('bass_swap_placement')}\n"
        f"{'=' * 60}\n\n"
    )
```

### RAG scorer — _score_example

```python
if concept and ex.get("id") in concept.get("example_ids", []):
    score -= 0.8  # strong boost for concept-matched examples
```

### direct_mix — build_prompt

Prepend concept block to prompt output.

### CLI — cli.py

```
python cli.py mix ./tracks --concept sunrise
python cli.py mix ./tracks --concept peak_time --min-minutes 45
```

`--concept` flag loads the concept, passes it through to `direct_mix` and `plan_transition` call chain.

---

## 7. Normalizer Changes

- Allow `loop_bars: 2` (currently enforces minimum of 4)
- Keep `loop_bars: 1` forbidden — too short to be useful, creates timing instability

---

## 8. Implementation Order

1. `normalizer.py` — allow `loop_bars: 2`
2. Trim `dj_skill.md` to ~300 lines
3. Trim `_TASK_PROMPT` and `_PLAN_TASK_SUFFIX` in `mix_director.py`
4. Create `claude-dj/concept_bank/` directory
5. Write all 10 concept JSON files
6. Add `load_concept()` to `mix_director.py`
7. Wire Phase 1, Phase 2, RAG, `direct_mix` injection points
8. Add `--concept` flag to CLI
9. Test: run a mix with `--concept sunrise` and `--concept peak_time`, verify prompt injection appears in logs, verify action sequences reflect the concept
