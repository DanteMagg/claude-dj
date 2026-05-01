# AI DJ System — Mixing Skill & Knowledge Base

> Reference document for an AI DJ system mixing 4/4, phrase-based electronic dance music (deep house, tech house, house, progressive house, techno, trance, EDM/big room, with D&B as edge case). Rules below are prescriptive defaults. Override only when explicit conditions in the rules are met.

---

## 0. QUICK REFERENCE — CRITICAL RULES

These are the highest-priority constraints. Violations are audibly bad.

1. **Never run two basslines simultaneously.** Hard rule. The incoming track's low band (≈20–200 Hz) must be cut to −∞ (full kill) before its volume fader is raised. Bass swap occurs at a phrase boundary, not gradually.
2. **Never run two lead vocals or two melodic leads simultaneously** for more than 2 bars. Vocals expose key clashes more than any other element.
3. **All transitions start on a phrase boundary** — preferably a 16- or 32-bar boundary (a 32-beat or 64-beat downbeat). Phrase boundaries take priority over BPM proximity, key compatibility, or anything else.
4. **Default harmonic move set (Camelot):** same key, ±1 on the wheel (perfect fifth/fourth), or A↔B at the same number (relative major/minor). All four are "safe."
5. **BPM matching tolerance:** keep absolute pitch shift within ±3% (≈±4 BPM at 128). Beyond that, use a tempo-bridge track or a breakdown to mask the shift.
6. **Default transition direction:** outgoing track's **OUTRO** over incoming track's **INTRO**. Never mix into a drop. Never mix out of an intro.
7. **Bass swap timing:** outgoing low EQ is killed *on the downbeat* where the incoming bassline enters — not before, not after.
8. **Energy step rule:** energy level changes by **±1 per transition** by default; ±2 only at planned peak/reset moments; never ±3 outside an explicit double-drop or set climax.
9. **Drop-into-drop (double drop) is a deliberate set-piece**, not a default. Default behavior is intro-over-outro.
10. **When in doubt, mix during a drum-only / percussion-only window.** Drums carry no harmonic content and forgive every kind of clash.

---

## 1. HARMONIC MIXING (CAMELOT WHEEL)

### 1.1 The wheel — full ruleset

The Camelot Wheel maps the 24 musical keys onto a 12-position clock, with an inner ring (A = minor) and outer ring (B = major). All compatibility relationships derive from circle-of-fifths theory.

**Compatible moves from any starting key `nX`** (where `n` ∈ 1–12, `X` ∈ {A, B}):

| Move | Camelot operation | Musical relationship | Energy effect | Use freely? |
|---|---|---|---|---|
| Same key | `nX → nX` | Identical key | Neutral, longest possible blend | YES — always safe |
| Perfect fifth up | `nX → (n+1)X` | Up a fifth (dominant) | Slight lift, brighter | YES — safe |
| Perfect fifth down | `nX → (n−1)X` | Down a fifth (subdominant) | Slight relaxation, warmer | YES — safe |
| Relative major/minor | `nA ↔ nB` | Same number, swap letter | Mood change (sad↔happy), no pitch clash — shares all 7 notes | YES — safe |
| Diagonal | `nA → (n+1)B` or `nB → (n−1)A` | Mode mixture; shares 6 of 7 notes | Subtle color shift | YES with care — works for most tracks |
| +2 on number, same letter | `nX → (n+2)X` | "Energy boost" — up two semitones | Strong lift, +1 to +2 energy | OCCASIONAL — only short blends, ≤16 bars overlap |
| +7 on number, same letter (≡ −5) | `nX → (n+7)X` | Up one semitone | "Modulation lift," very noticeable | OCCASIONAL — short blends only |
| Same number, +3/−3 with letter swap | `nB → (n−3)A` | Parallel major↔minor (e.g., F major → F minor) | Dramatic mood flip | RARE — only as a set-piece |

**Wrap-around rule:** Camelot numbers wrap modulo 12, so `12 + 1 = 1`, `1 − 1 = 12`. Letter does not wrap.

**Diatonic logic:** the same key and the four neighbors (±1 in either ring, A↔B on same number) are the four chords most closely related to the source key. Any of these will sound consonant.

**Distance penalty:** each step away from the source on the wheel is a more dissonant move. Beyond 2 numeric steps with the same letter, treat as effectively unrelated; do NOT attempt a melodic blend.

### 1.2 Breaking the rules — when, and how to get away with it

Rule-breaking is permitted under specific, narrow conditions:

1. **Short overlap (≤8 bars) only.** A non-compatible mix sounds bad in long blends because the listener has time to register the dissonance. Cut the overlap window short.
2. **Mix during a percussion-only / drum-break section** of one or both tracks. Drums have no defined key. This is the universal damage-limitation move.
3. **Cut the mids (200 Hz – 5 kHz) of the outgoing track during the overlap.** Mids carry the most key-defining content (vocals, lead synths, chord stabs). Killing mids during a clash hides it.
4. **Use it intentionally as an "energy boost" / "gear shift"** — typically +2 semitones (`+2` on Camelot number). The audience will perceive a deliberate lift, not a mistake. Use sparingly (≤1 per 30 minutes) or it loses impact.
5. **Use a percussive / rhythm-tool track as a bridge.** A 16- to 32-bar drum loop placed between two harmonically incompatible tracks resets the harmonic context.
6. **Pitch-shift the incoming track** using key-shift / key-lock features. Shifting up to ±2 semitones is generally transparent; beyond that it audibly degrades timbre.

### 1.3 Key clash — audible symptoms

The AI must recognize these signatures as "key clash detected, terminate or shorten transition":

- **"Sour" or "out-of-tune" bass** — most obvious in long sub-bass notes that don't share a root pitch class.
- **Beating / chorusing on sustained pads** — two near-but-not-identical pitches produce slow amplitude oscillation (~0.5–5 Hz).
- **Wandering vocal pitch** — vocal sounds flat or sharp against the new harmonic background.
- **Muddy lower-mids (200–500 Hz)** — clashing chords pile up in this range as dissonant inharmonics.
- **Audience response drop** — heads stop nodding, hands drop. Treat as runtime feedback signal if available.

### 1.4 Vocal handling — why vocals are most key-sensitive

Vocals are the most sensitive element in a mix to key mismatches for three structural reasons:

1. **Clear fundamental pitch.** Unlike percussion or supersaw stacks, a sung note has a single, prominent fundamental that the ear locks onto. Two different sung pitches an interval apart create unambiguous dissonance.
2. **Mid-range placement.** Vocal fundamentals sit in 100–1100 Hz with formants up to 5 kHz — squarely in the most perceptually sensitive region of the human hearing curve.
3. **Linguistic/melodic salience.** The brain attends to vocals as primary signal (foreground), so any pitch error is consciously processed rather than masked.

**Operational rules for vocals:**

- **Two vocals never overlap for more than 2 bars** unless the keys are identical or relative (`nA ↔ nB`).
- When mixing into a track with a vocal, **cut the outgoing track's mids (200 Hz – 5 kHz) by ≥6 dB** before the new vocal enters.
- **Acapella over instrumental requires same key or +1 / −1 on the wheel.** No exceptions for long blends.
- **End the outgoing vocal phrase before the incoming vocal phrase begins.** Align lyrical phrasing if possible: outro-vocal-tail → intro-vocal-head, with no overlap.
- If forced to mix two vocals in incompatible keys, use a sharp **cut** (instant fader swap on a downbeat), not a blend.

---

## 2. GENRE PROFILES — BPM, STRUCTURE, ENERGY, TRANSITIONS

All genres below are 4/4. Phrases are 8 bars (32 beats) by default; section lengths are 16/32/64 bars.

### 2.1 Deep House
- **BPM:** 118–125 (median 122). Operate at 120–124 unless leaning lo-fi/dub.
- **Structure:** 16-bar intro → 16–32-bar groove → 16-bar light breakdown → 32-bar main → 16-bar outro. Drops are subdued — no trance-style breakdown/drop architecture.
- **Energy arc:** flat-to-gradual rise. Energy 3–6 on a 1–10 scale.
- **Transitions:** **long blends, 32–64 bars.** Use full intro-over-outro. Bass swap on the 32-bar boundary. Rotary-style EQ blending preferred over cuts.
- **Good vs bad:** Good = patient, both grooves overlap for ≥16 bars with bass swap mid-overlap. Bad = quick cuts (the genre's warmth depends on overlap), cutting groove during a vocal phrase.

### 2.2 Tech House
- **BPM:** 124–128 (median 126). Most common sweet spot.
- **Structure:** 16–32-bar intro (drum-only or drum + bass) → 32-bar groove → 16-bar break → 32-bar main → 16-bar outro. Vocal hooks are typically chopped, ≤2-bar fragments.
- **Energy arc:** flat. Tech house is the workhorse — energy 5–7, sustained.
- **Transitions:** **medium-long blends, 16–32 bars.** Rolling hat patterns let you create polyrhythmic interest during overlap; use it. Bass swap is critical because basslines are the genre's identity.
- **Good vs bad:** Good = bass swap on the 32-bar mark with hats interlocking through the overlap. Bad = mixing through the chopped-vocal hook (hooks are mid-heavy and clash), or cutting before the bass swap completes.

### 2.3 House (general / mainstream / vocal house)
- **BPM:** 120–128 (median 124–125).
- **Structure:** Often verse-chorus influenced. 16-bar intro → verse → chorus → bridge → breakdown → chorus → 16-bar outro. Phrases are 8 or 16 bars.
- **Energy arc:** wave shape — climbs to chorus, dips at breakdown, peaks at final chorus.
- **Transitions:** 16–32 bars. Respect choruses (never cut mid-chorus); mix outro-into-intro or post-final-chorus into next intro.
- **Good vs bad:** Good = chorus-end of A → intro of B with bass swap on the chorus's last downbeat. Bad = bringing in B during A's chorus (vocal collision).

### 2.4 Progressive House
- **BPM:** 120–128. Two camps: classic/underground 120–124, festival progressive 126–130.
- **Structure:** Long. 32-bar intro → 32-bar build → 32-bar groove → 32-bar breakdown (often melodic/cinematic) → 32–64-bar drop → 32-bar outro. Tracks frequently 7–10 minutes.
- **Energy arc:** slow, narrative wave. Build → release → build → bigger release. Energy 4–9 across a track.
- **Transitions:** **very long blends, 32–64 bars.** Layer pads and atmospherics. Harmonic compatibility matters most here — melody is foregrounded.
- **Good vs bad:** Good = blend the outro pads of A into the intro pads of B over 64 bars, with bass swap inside that window. Bad = quick cuts (kills the storytelling), or any harmonic clash (audible because of long pads).

### 2.5 Techno
- **BPM:** 125–150. Subdivide:
  - **Hypnotic / dub techno:** 125–130
  - **Peak time / driving:** 130–138
  - **Hard techno / industrial:** 138–150
- **Structure:** 64-bar intro → 32-bar build with element-add every 16 bars → 64–128-bar main groove with micro-variations → 32-bar breakdown (filter sweep, FX wash) → 64-bar second main → 64-bar outro. Designed for long mixes.
- **Energy arc:** linear and hypnotic. Energy increments slowly via element addition (a hat, a stab, a filter open) every 16 or 32 bars.
- **Transitions:** **32–64 bars** with surgical EQ. Bass swap is essential — techno bass is often a single sustained note that will produce phasing if doubled. FX (reverb, delay, filter) used sparingly.
- **Good vs bad:** Good = align kick on first downbeat of the 64-bar boundary, bass swap at bar 16 of the overlap, full mids handover by bar 32. Bad = trying to mix during a melodic stab phrase (clashes), or stacking two kicks with phase offset (sounds like a flam).

### 2.6 Trance — Progressive Trance
- **BPM:** 128–134 (median 130).
- **Structure:** 32-bar intro → 32-bar build → 32–64-bar main → 32-bar breakdown (the "story" — pads, melody) → riser → 32-bar drop → 32-bar outro.
- **Energy arc:** classic wave. Energy 5 → 8 across a track.
- **Transitions:** 32–64 bars. Long blends; melody-first genre, so **harmonic compatibility is mandatory** (same key, ±1, or A↔B only).
- **Good vs bad:** Good = breakdown-of-A overlapped with intro-of-B; the breakdown is drumless or sparse, masking any minor incompatibilities. Bad = mixing across two melodic breakdowns simultaneously (instant melodic clash).

### 2.7 Trance — Uplifting / Epic
- **BPM:** 134–142 (median 138).
- **Structure:** 32-bar intro → 32-bar build → 32-bar main → **64-bar extended emotional breakdown** (melody, choir, climax cue) → riser → 32-bar climactic drop → 32-bar outro.
- **Energy arc:** strong wave. Peak energy 9–10 at the climactic drop.
- **Transitions:** 32 bars typical. **Mix breakdown-to-breakdown or outro-to-intro.** Never overlap two anthemic drops unless explicitly double-dropping (high risk in this genre due to melodic density).
- **Good vs bad:** Good = blend during the long breakdown of A as B's intro begins; both tracks are minimal there. Bad = mixing during A's climactic lead phrase (the lead is too dominant to share airspace).

### 2.8 Trance — Psytrance
- **BPM:** 138–150. **Progressive psy** 134–140; **full-on / Goa** 142–148; **darkpsy** 148+.
- **Structure:** 16–32-bar intro → continuous evolving 32-bar groove sections separated by 16-bar breaks/risers → 16-bar outro. Less verse-chorus, more continuous-build.
- **Energy arc:** linear ascent within a track; sets are arranged as continuous climbs.
- **Transitions:** 16–32 bars. The signature rolling 1/16-note bassline means bass swaps must be **clean and instant** — overlapping psy basslines is catastrophic. Use breaks/risers as transition windows.
- **Good vs bad:** Good = bass swap during a 16-bar break in A. Bad = any overlap of two rolling basslines (immediate phase mess).

### 2.9 EDM / Big Room
- **BPM:** 126–132 (almost always 128).
- **Structure:** 16–32-bar intro → 16-bar build → 16–32-bar drop (very minimal — kick + lead stab) → 16-bar break → 16-bar build #2 → 32-bar drop #2 → 16-bar outro. Total runtime often only 3–4 minutes.
- **Energy arc:** binary — minimal during builds/breakdowns, maximum during drops. Energy 3 → 10 → 3 → 10.
- **Transitions:** **shorter than house/techno, 16 bars typical**, because intros/outros are shorter. Drops are dry and minimal (fewer harmonic elements), so double-drops are genre-native and expected here.
- **Good vs bad:** Good = align the build of A with the build of B (each 16 bars), drop both on the downbeat. Bad = mixing into the middle of a drop (no headroom, will distort/clip due to genre's high RMS).

### 2.10 Drum & Bass (edge case / contrast genre)
- **BPM:** 170–180 (median 174). DJ software often displays as half-time (≈87) for pairing with hip-hop.
- **Structure:** 32-bar intro (often percussion + sub only, no breakbeat) → 16-bar build → 32-bar drop with full Amen-derivative breakbeat → 32-bar second main → 32-bar outro. Halftime D&B uses kick-on-1, snare-on-3 over the 174 BPM grid.
- **Energy arc:** binary like EDM, but with much faster harmonic motion.
- **Transitions:** **decisive — 8 or 16 bars, not 32+**. The high BPM makes long blends sound cluttered. **Double-drop is the genre's signature move.** Spinbacks and wheel-ups are culturally accepted.
- **Half-time / double-time pairing:** D&B at 174 ≈ hip-hop at 87 (half-time), and ≈ techno at 130 with 2:1 ratio. Use these mathematical relationships for cross-genre transitions.
- **Good vs bad:** Good = mix outro-A drum tool into intro-B drums-only with bass swap at bar 8 of the overlap; or align drops for a double-drop. Bad = long melodic blend (the breakbeat density makes it noisy), or mixing into a drop without phrase alignment.

### 2.11 Cross-genre BPM gradient (for reference)

```
Deep House  Tech House  House  Prog House  Techno  Big Room  Prog Trance  Uplifting  Psy   D&B
118–125     124–128    120–128 120–128    125–150 126–132   128–134      134–142    138–150 170–180
```

When transitioning between genres, prefer adjacent boxes. Two-box jumps (e.g., deep house → big room) require either a bridge track or a breakdown-masked tempo shift.

---

## 3. TRANSITION TECHNIQUES

### 3.1 EQ mixing — bass swap protocol

The bass swap is the single most important EQ move. Default protocol:

1. **T−16 bars** (16 bars before phrase boundary): incoming track's low EQ at full kill (−∞ / −26 dB or however the mixer permits). Mid and high EQ at 12 o'clock.
2. **T−16 to T−4:** raise incoming volume fader to full. Outgoing remains at full with all EQ at 12 o'clock.
3. **T = phrase boundary downbeat:** simultaneously kill outgoing low EQ and restore incoming low EQ to 12 o'clock. This is one motion, on the downbeat.
4. **T+8 to T+16:** swap mids. Cut outgoing mid by 6–12 dB (don't full-kill mids — sounds unnatural). Bring incoming mid to 12 o'clock if it was reduced.
5. **T+16 to T+32:** swap highs. Hi-hats are perceptually sensitive — reduce outgoing high gradually (over ≥4 bars) rather than cutting.
6. **T+32 (or end of phrase):** outgoing volume fader down. Mix complete.

**Order summary:** lows swap first (instant, on a downbeat), mids swap second (gradual, ≤8 bars), highs swap last (most gradual).

**Genre-specific timing adjustments:**

| Genre | Swap window (T to fader-down) |
|---|---|
| Deep house, prog house, prog trance | 32–64 bars |
| Tech house, house, techno | 16–32 bars |
| Uplifting trance, psy | 16–32 bars |
| EDM/big room | 8–16 bars |
| D&B | 8–16 bars |

### 3.2 Stem layering order (when stem separation is available)

Tracks decompose into 4 stems: **drums, bass, vocals/lead, other (pads/chords/instruments)**. Standard introduction order for the incoming track:

1. **Drums first** (specifically hi-hats and percussion — not full kit). Layer over outgoing track's drums at low volume; do not introduce incoming kick yet.
2. **Other / atmospheric layer** (pads, chords) — bring in over 8–16 bars after drums establish.
3. **Bass / sub** — only at the bass-swap downbeat, with simultaneous outgoing bass kill.
4. **Vocals / lead** — last. Vocals enter only after bass swap is complete and outgoing vocal has ended.

For the outgoing track, mute stems in **reverse** order: vocals first, then other, then bass (at the swap point), then drums last.

**Rationale:** drums and pads are tonally neutral / forgiving. Bass and vocals are the conflict-prone elements; they get the shortest co-existence window.

### 3.3 Crossfade length heuristics

| Energy level / genre context | Default overlap |
|---|---|
| Deep house, ambient warm-up | 48–64 bars |
| Progressive house, prog trance, melodic techno | 32–48 bars |
| Tech house, peak techno, house | 16–32 bars |
| Uplifting trance, psy, EDM | 16 bars |
| D&B, hip-hop, fast cuts | 8 bars |
| Energy boost / surprise / "cut" mix | 1–4 bars (instant cut on downbeat) |

**Rule:** longer overlap = more demanding harmonic compatibility. A 64-bar blend MUST be on the same key, ±1, or A↔B. A 16-bar blend tolerates a diagonal or +2 move.

### 3.4 The "energy dip" technique

Best transition windows are **low-energy moments inside both tracks** — places where harmonic and rhythmic density is lowest. In priority order:

1. **Outgoing track's outro** (16–32 bars from end) — sparsest section, designed for mixing.
2. **Outgoing track's first/secondary breakdown** (mid-track, after first chorus or main) — drumless or near-drumless, ideal for introducing a new track's drums.
3. **Outgoing track's final-chorus tail** — energy is descending toward the outro.
4. **Outgoing track's intro** (last 16 bars of it, if no full outro available) — emergency-only.

**Avoid as transition windows:**
- Drops / main groove / chorus of outgoing track (highest density).
- Build-ups / risers (the audience is anticipating a specific resolution; switching tracks during a riser breaks the contract).
- The first 8 bars of any new section (the section is establishing — let it land).

**Rule of thumb:** **scan the outgoing track for its lowest-density 16-bar window in the second half.** Begin the incoming track such that that low-density window aligns with the incoming track's intro phrase.

### 3.5 Double-drop technique

A double-drop aligns the drop of two tracks so they hit on the same downbeat. Hard rules:

1. **Both tracks must be the same BPM** (within 0.1 BPM after sync). No tempo bend is acceptable into a double-drop.
2. **Both tracks must be harmonically compatible** (same key, ±1, or A↔B). A clash will be at maximum loudness.
3. **One track must be sonically simpler** at the drop — preferably a "tool" with minimal melodic content, or an instrumental version. Two full-vocal drops will mud.
4. **Bass swap is impossible** during a double-drop — both basslines will play. Therefore at least one track must have a sub-only / non-melodic bassline, or one must have its low EQ cut and ride only mids/highs.
5. **Phrase alignment is mandatory** — drops on bar 1 of both tracks' drop sections, on the same downbeat.
6. **Native to D&B and big-room EDM**, occasional in techno, **rare/avoid in deep house, prog house, trance** (those genres' drops are too melodically dense).
7. **Use sparingly** — a double-drop is a set-defining moment, not a routine transition. ≤2–3 per hour-long set.

### 3.6 Damage limitation — incompatible-key transitions

When the next track must be played but is harmonically incompatible (more than ±2 on the wheel and not a relative-key relation):

1. **Shorten the overlap to ≤8 bars.** Long overlaps reveal the clash.
2. **Mix during a percussion-only window** in either track. Drum breaks have no harmonic content.
3. **Cut mids on outgoing track by 12 dB** during overlap.
4. **Use a high-pass filter sweep** on outgoing — filtering out everything below ~500 Hz removes most of the harmonic content, leaving rhythmic/percussive elements that don't clash.
5. **Use a one-shot effect** (reverb tail, white-noise sweep, vinyl-stop, echo-out) to mask the moment of swap. ~1 bar of FX wash followed by the new track at full.
6. **Cut, don't blend.** A clean instant-cut on a downbeat is preferable to a 16-bar harmonic clash.
7. **Bridge with a percussion tool track** — a 32-bar drum-only loop placed between A and B resets the harmonic context entirely.
8. **Pitch-shift incoming track** by ±1 or ±2 semitones using key-shift to reach a compatible key. Acceptable timbre cost up to ±2 semitones.

### 3.7 Why transitions into drops are bad — and into breakdowns/intros are good

- **A drop is the audience's payoff.** They have been built up to expect it from the preceding 16–32 bars of riser. Transitioning the track *at the drop* substitutes a new, unfamiliar piece of music for the expected payoff — the contract is broken, the dancefloor reads it as a mistake.
- **A drop has maximum frequency density, maximum RMS, and maximum melodic salience.** Layering anything over a drop creates clutter and clipping. The mix headroom is gone.
- **Transitioning *into* a breakdown** works because breakdowns are sparse — there is room for a new track's drums or pads to enter without conflict.
- **Transitioning *into* an intro** works because intros are designed to be DJ-friendly: drum-and-percussion-only or minimal harmonic content for 16–32 bars.
- **Operational rule:** the AI's incoming-track cue point is at the **start of the incoming intro**, and the outgoing-track exit point is at the **start of an outgoing breakdown or outro** — not mid-drop, not mid-chorus.

---

## 4. ENERGY ARC AND SET STRUCTURE

### 4.1 Set-level energy progression

Energy on a 1–10 scale (Mixed In Key convention). Default arcs:

| Set type | Length | Arc shape |
|---|---|---|
| Warm-up | 60–120 min | Energy 3 → 6, monotonic rise, never exceeds 7 |
| Peak time | 60–120 min | Energy 6 → 9, plateaus + steps + ≥1 wave dip |
| Closing | 60–120 min | Energy 8 → 4, monotonic descent with 1–2 small lifts |
| Festival mainstage | 45–90 min | Energy 7 → 10, fast rise, sustained, single descent at end |
| Open-to-close | 6–8 hr | Full sinusoidal: 3 → 7 → 9 → 7 → 9 → 6 → 4 |

### 4.2 Energy step rules (per transition)

- **Default:** ±1 energy level per transition. Imperceptible to crowd, cumulative effect across set.
- **Plateau blocks:** hold energy steady for 3–4 consecutive tracks, then step up. Creates "chapters."
- **Permitted ±2 jumps:** at deliberate set-section boundaries (warm-up → peak; before a big drop). Limit to **2–4 per hour**.
- **Forbidden ±3+ jumps** unless: (a) the entire dancefloor is at peak attention, (b) the move is a planned set-piece (e.g., a known anthem drop), (c) the prior track was specifically chosen as a setup.
- **Energy *drops* are harder than energy *rises.*** A drop of −2 or more without a breakdown-mediated reset will read as "the energy died." Always mediate big drops via a breakdown, a filter sweep, or a sparse percussion tool.

### 4.3 BPM progression rules

- **Within a section:** ±1 BPM per transition or hold steady. Cumulative drift of +5 to +10 BPM across a set is acceptable and largely imperceptible.
- **Between sections:** ±2–4 BPM jump permitted at a clear section boundary (mediated by breakdown).
- **Big BPM jump (>5 BPM):** require a tempo-bridge track that overlaps both ranges, a breakdown to mask the change, or a half-time/double-time mathematical relationship (e.g., 87 BPM ↔ 174 BPM).
- **Master tempo / key-lock should be ON by default** — pitch-shift via tempo change beyond ±3% audibly degrades timbre.

### 4.4 Reading breakdowns and drops for transition timing

- **Outgoing breakdown** (typically at ⅔ to ¾ through the track) is the **second-best** transition window after the outro. Expect duration: 16–32 bars.
- **Outgoing drop** (right after a breakdown) — DO NOT START a transition here. This is the audience-payoff section. Transitions started here will be perceived as cutting the song short.
- **Incoming intro start** — this is your primary cue-in point. Place a cue point at the first downbeat of the intro.
- **Incoming first drop** — for a double-drop or aligned-drop transition, this is the alignment target. Otherwise irrelevant.

### 4.5 Phrase alignment — why 8/16/32 boundaries matter

- **4/4 dance music is hierarchically structured:** 4 beats per bar → 8 bars per phrase (32 beats) → 16/32 bars per section. Producers place new elements (a hat introduction, a synth stab, the bassline drop) at the start of these boundaries.
- **A transition that crosses a phrase boundary in alignment with the music** sounds intentional — both tracks have a "new element entering" moment at the same downbeat.
- **A transition starting mid-phrase** sounds like a mistake — one track has an in-progress phrase while the other has just started. The brain registers the asymmetry.
- **Operational rule:** every fader/EQ event in a transition should land on a **bar 1 downbeat**, ideally bar 1 of an 8-bar (32-beat), 16-bar (64-beat), or 32-bar (128-beat) phrase. Use cue points at these boundaries.
- **Quantize must be ON** for any beat-jumps or loop operations. Hot cues should be set on phrase boundaries, not arbitrary positions.

### 4.6 First track / opening track rule

- Open at **60–70% of intended peak energy.** Establishes momentum without exhausting headroom.
- Choose an opener with **a long, DJ-friendly intro** (16–32 bars of drums or sparse texture) so the incoming-from-silence start sounds intentional.

---

## 5. COMMON MISTAKES — DETECTION AND PREVENTION

### 5.1 Bass clash (two basslines simultaneously)
- **Symptom:** muddy, thick low-end; possible audible phase cancellation; level meters peaking; system limiter audibly engaging on drops.
- **Cause:** failure to kill incoming low EQ before raising volume fader.
- **Prevention:** **incoming low EQ at full kill before fader is raised.** Bass swap occurs as a single instantaneous event on a downbeat.
- **Detection at runtime:** if low-frequency RMS exceeds the running average of either solo track during overlap, terminate overlap immediately.

### 5.2 Vocal clash
- **Symptom:** two voices audible simultaneously; pitch instability; lyrical/intelligibility loss.
- **Cause:** overlap window too long, or starting incoming vocal before outgoing vocal phrase ends.
- **Prevention:** never overlap two leads/vocals for >2 bars. Cut outgoing mids by ≥6 dB when incoming vocal enters. Align lyrical phrasing — outgoing vocal should END (with its natural decay) before incoming vocal begins.

### 5.3 BPM drift / beat misalignment
- **Symptom:** flam (two slightly offset kicks audible as a doubled hit); kicks gradually drifting out of phase across the overlap; stuttering / phasing on hats.
- **Cause:** beatgrid inaccuracy, pitch-fader nudge needed, source track has variable tempo (live drumming, older productions).
- **Prevention:** pre-analyze beatgrids for accuracy; for tracks with drift, use sync with **flexible beatgrid** mode; for short overlaps, a few BPM of mismatch is tolerable; for long overlaps (>32 bars) BPM must match within 0.1 BPM.
- **Operational rule:** if one of the tracks has unreliable beatgrid, keep overlap ≤8 bars and cut on downbeat.

### 5.4 Wrong phrase boundary
- **Symptom:** new element from incoming track lands mid-phrase, sounds out of place; sections of the two tracks misalign such that breakdown-A is over groove-B, etc.
- **Cause:** failure to count bars from the start of the section; bringing in incoming track on bar 5 of an 8-bar phrase.
- **Prevention:** all cue points and transition events on bar 1 of an 8-bar phrase minimum, ideally a 16- or 32-bar phrase. Count bars from the first kick of the section, not from arbitrary track start.

### 5.5 Energy mismatch
- **Symptom:** dancefloor empties on a transition; sudden silence in crowd reaction; audience moves to bar.
- **Cause:** energy jump too large (>±2 outside set-section boundary), or BPM jump perceived as abrupt, or genre swerve too sharp.
- **Prevention:** maintain ±1 energy level per transition by default; mediate large jumps with a breakdown, a bridge track, or a deliberate pause/FX wash; do not change two dimensions (BPM AND energy AND genre) simultaneously — change one at a time across consecutive transitions.

### 5.6 Other prevention rules (tertiary)
- **Mixer level / clipping:** keep channel meters peaking in the green-to-yellow range; never ride into the red. Drops that hit a hardware limiter will read as quieter, not louder.
- **Quantize on for loops and beat-jumps.** Otherwise loop length will be off by fractional beats and accumulate phase error.
- **Use key-lock** when pitch-shifting beyond ±2% to avoid pitch-induced key clash.
- **Effects are accents, not crutches.** Excessive reverb/delay during every transition reads as a tell that the underlying mix isn't working. Apply effects on phrase boundaries, in time with the track tempo (1/4, 1/8, 1/16 in sync with BPM).

---

## 6. OPERATIONAL DECISION CHECKLIST (per transition)

Before executing any transition, the AI should resolve the following in order:

1. **Phrase position:** is the transition aligned to a 16- or 32-bar boundary in BOTH tracks? If no, defer.
2. **BPM compatibility:** is |ΔBPM| ≤ 4 BPM (or a half/double-time relationship)? If no, plan a bridge.
3. **Key compatibility:** is the move on the safe set (same / ±1 / A↔B / diagonal)? If no, shorten overlap to ≤8 bars and apply damage-limitation EQ.
4. **Section alignment:** is outgoing in outro/breakdown AND incoming in intro? If no, find different cue points.
5. **Energy step:** is ΔEnergy within ±1 (or justified ±2)? If no, insert a bridge track.
6. **Vocal collision:** will two vocals overlap for >2 bars? If yes, replan timing or shorten overlap.
7. **Bass swap timing:** is there a clear downbeat for the bass swap inside the overlap window? If no, replan.
8. **Crossfade length:** chosen per genre table (3.3).
9. **Stem layering order:** drums → other → bass(swap) → vocals.
10. **Execute.**

If any check fails and cannot be resolved, default to a **short percussion-window cut** (8 bars, drum-only, instant fader swap on downbeat) — the universal damage-limitation transition.

---

## 7. LOOP TECHNIQUE

### 7.1 Purpose — three legitimate uses

**Use 1 — Extend the outgoing track's transition window.** When the outro is too short (≤8 bars of clean material), loop its cleanest drum-only phrase to create the runway needed for a proper bass swap + handover. This is the most common professional loop application.

**Use 2 — Hold a peak moment.** After the drop lands and the crowd is responding strongly, loop the drop's first 8-bar phrase to sustain peak energy before transitioning. Use only when the floor is clearly at maximum — otherwise it reads as a stall.

**Use 3 — Pre-drop tension hold.** Loop the last 8 bars of a build to stretch anticipation before the drop fires. This works because the listener is primed for release; a one-phrase extension amplifies the payoff. Beyond 1 repeat it deflates instead.

### 7.2 What to loop — and what never to loop

**Loop these (safe):**
- Drum-only / hi-hat-only phrases — no harmonic content, loops transparently
- Outro percussion tail where the bassline has already dropped out
- The first 8 bars of a breakdown (sparse, low-density, harmonically neutral)

**Never loop these:**
- Melodic or chord stab phrases — the repetition is immediately audible; sounds like a skip
- Vocal phrases — a looped vocal reads as a technical error, not a creative choice
- The main groove with full bassline — tolerable for 1 repeat at most, fatiguing beyond that
- Intro sections — loops there have no payoff; the track hasn't established yet

### 7.3 Technical rules (binding)

1. **`start_bar` must be a multiple of 8.** Mid-phrase loop points sound like a glitch regardless of content.
2. **`loop_bars` must be 4 or 8.** 8-bar is the default for house/techno. 4-bar for D&B or tight builds.
3. **`loop_repeats` 1–3.** One repeat = 8 bars of extension (standard). Two repeats = 16 bars (only for a planned outro extension). Three = only in peak techno with clear audience signal. Four is almost always too long.
4. **Post-loop source mechanics — understand this before writing actions:**
   After the loop, the track automatically resumes from source bar `start_bar + loop_bars * loop_repeats`.
   - **Fade-out (typical):** emit `fade_out` at `start_bar: (start_bar + loop_bars * loop_repeats)`. No play needed.
   - **Continue / drop (use case 3):** emit NO play — the source lands naturally on the next section. **Use 1 repeat only**; 2+ repeats will skip ahead past the intended drop.
   - **T2 fade_in during the loop:** valid and useful — the stable loop window gives T2 a runway to blend into.
   - **Do NOT place a `loop` and a `fade_out` at the same bar** for the same track.
5. **One loop per transition maximum.** If T1's outro was looped, T2's outro does not get one.
6. **Do not loop consecutive transitions.** Overuse eliminates the effect entirely.

### 7.4 Use by genre

| Genre | Primary use | Preferred config |
|---|---|---|
| Deep house | Extend short outro for long blend | 8 bars × 1–2 repeats |
| Tech house | Hold peak drop phrase | 8 bars × 1 repeat |
| Progressive house | Pre-drop tension | 8 bars × 1 repeat |
| Techno | Extend outro drum section | 8 bars × 1–3 repeats |
| Uplifting trance | Pre-drop tension only | 8 bars × 1 repeat |
| Psytrance | Emergency extension only | 4 bars × 1 repeat |
| EDM/big room | Pre-drop 4-bar hold | 4 bars × 1 repeat |
| D&B | Emergency only (short outro) | 4 bars × 1 repeat |

### 7.5 The short-outro problem — canonical loop fix

Some tracks have abrupt endings: 8 bars of drums, then a fast fade. Standard protocol:

1. Identify the last clean 8-bar drum-only phrase before the track deteriorates.
2. Place `loop` on that phrase: `loop_bars: 8`, `loop_repeats: 2` = 16 bars of added runway.
3. Begin `fade_in` of the incoming track so the bass swap lands inside the loop window.
4. `fade_out` the outgoing track to close within or just after the loop window.
5. Do NOT emit a `play` for the outgoing track after the loop — it should be fading out.

---

## 8. PROFESSIONAL MIX EXAMPLES

These are canonical action sequences for common scenarios. Use them as structural templates.

### 8.1 Standard tech house transition (16-bar blend, same key)

**Situation:** T1 is in its outro (drums + bass, no vocals). T2 starts at its intro (drums only, 16 bars). Same key. 16-bar overlap is correct for tech house.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 64, "duration_bars": 16, "from_bar": 0,
   "stems": {"drums": 0.8, "bass": 0.0, "vocals": 0.0, "other": 0.6}},
  {"type": "bass_swap", "track": "T1", "at_bar": 72, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 80, "from_bar": 16},
  {"type": "fade_out",  "track": "T1", "start_bar": 80, "duration_bars": 16}
]
```

Bass held at 0.0 on T2 until the swap at bar 72 (halfway through the 16-bar overlap, on a phrase boundary). T1 fades over the 16 bars after T2 is already at full volume.

---

### 8.2 Deep house long blend with loop extension (outgoing has short outro)

**Situation:** T1 has only 8 bars of clean percussion before track ends. Need a 32-bar blend. Loop T1's percussion phrase twice for 16 bars of runway, then blend inside it.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "loop",      "track": "T1", "start_bar": 80, "loop_bars": 8, "loop_repeats": 2},
  {"type": "fade_in",   "track": "T2", "start_bar": 88, "duration_bars": 32, "from_bar": 0,
   "stems": {"drums": 0.6, "bass": 0.0, "vocals": 0.0, "other": 0.5}},
  {"type": "bass_swap", "track": "T1", "at_bar": 96, "incoming_track": "T2"},
  {"type": "fade_out",  "track": "T1", "start_bar": 96, "duration_bars": 24},
  {"type": "play",      "track": "T2", "at_bar": 120, "from_bar": 32}
]
```

Loop fires at bar 80 (last clean drum phrase), giving 16 bars of runway (bars 80–96). Fade_in starts at bar 88 — 8 bars into the loop, so T1 is already stable. Bass swap at bar 96 (phrase boundary, 8 bars into the 32-bar blend). Loop ends naturally at bar 96; fade_out takes T1 the rest of the way.

---

### 8.3 Short cut — harmonically incompatible tracks, percussion-window only

**Situation:** T1 and T2 are more than ±2 apart on the Camelot wheel. T1 has a 16-bar drum-only window in its outro. Only drums on T2 fade_in; no melodic elements introduced during overlap.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 56, "duration_bars": 8, "from_bar": 0,
   "stems": {"drums": 1.0, "bass": 0.0, "vocals": 0.0, "other": 0.0}},
  {"type": "bass_swap", "track": "T1", "at_bar": 64, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 64, "from_bar": 8},
  {"type": "fade_out",  "track": "T1", "start_bar": 56, "duration_bars": 16}
]
```

8-bar blend only — just long enough to establish T2's kick before the swap. `other: 0.0` and `bass: 0.0` on fade_in ensures zero harmonic content introduced during the clash window. Bass swap and T2 full-play fire on the same downbeat (bar 64) for a clean cut.

### 8.4 Progressive house structural blend (32-bar)

**Situation:** T1 is in its outro (elements stripping every 8 bars). T2's intro mirrors the process in reverse (elements adding every 8 bars). Aligned, they form a continuous composition. Same key.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 80, "duration_bars": 32, "from_bar": 0,
   "stems": {"drums": 0.5, "bass": 0.0, "vocals": 0.0, "other": 0.4}},
  {"type": "eq",        "track": "T1", "bar": 80, "low": 1.0, "mid": 0.8, "high": 1.0},
  {"type": "bass_swap", "track": "T1", "at_bar": 88},
  {"type": "eq",        "track": "T1", "bar": 96, "low": 0.0, "mid": 0.6, "high": 0.8},
  {"type": "play",      "track": "T2", "at_bar": 112, "from_bar": 32},
  {"type": "fade_out",  "track": "T1", "start_bar": 96, "duration_bars": 16}
]
```

T1's outro strips elements while T2's intro adds them; the 32-bar window gives both arcs room to breathe. Bass swap at bar 88 (8 bars in, first phrase boundary). Mid/high EQ on T1 rolls off progressively from bar 96 onward.

---

### 8.5 Filter sweep -- key-incompatible tracks

**Situation:** T1 and T2 are >2 steps apart on Camelot. Use frequency-domain separation: T1 exits on low-pass (bass/kick only), T2 enters on high-pass (hats/highs only), then both filters remove and T2 is full-frequency. No harmonic content overlaps during the swap.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 64, "duration_bars": 8, "from_bar": 0,
   "stems": {"drums": 0.9, "bass": 0.0, "vocals": 0.0, "other": 0.0}},
  {"type": "eq",        "track": "T1", "bar": 64, "low": 1.0, "mid": 0.3, "high": 0.2},
  {"type": "bass_swap", "track": "T1", "at_bar": 72},
  {"type": "play",      "track": "T2", "at_bar": 72, "from_bar": 8},
  {"type": "fade_out",  "track": "T1", "start_bar": 64, "duration_bars": 16}
]
```

T1's mid and high EQ are killed at bar 64, leaving only its kick/sub. T2's `other:0.0` and `bass:0.0` mean only its hats come through. The two tracks occupy non-overlapping frequency bands for the 8-bar window -- zero harmonic clash. Bass swap at bar 72 clears T1's sub and T2 goes full-frequency.

---

### 8.6 Breakdown swap -- T1 breakdown as transition runway

**Situation:** T1 has a 16-bar breakdown (kick removed, melody sparse). Use it as the transition runway: T2's intro enters during T1's quiet breakdown, then T1 is killed just before it would re-drop, giving T2's drop to the crowd.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 56, "duration_bars": 16, "from_bar": 0,
   "stems": {"drums": 0.6, "bass": 0.0, "vocals": 0.0, "other": 0.3}},
  {"type": "bass_swap", "track": "T1", "at_bar": 64},
  {"type": "play",      "track": "T2", "at_bar": 72, "from_bar": 16},
  {"type": "fade_out",  "track": "T1", "start_bar": 64, "duration_bars": 8}
]
```

T2 enters quietly at bar 56 during T1's breakdown. Bass swap at bar 64 (start of what would be T1's re-drop). T1 fades fully by bar 72 -- the crowd gets T2's drop as the release moment instead. T2 `play` at bar 72 `from_bar: 16` picks up at T2's first drop.

---

### 8.7 Echo-out -- hard key change with FX bridge

**Situation:** T1 and T2 are harmonically incompatible. Use echo-out: T1 exits on a reverb/delay tail that masks the key change, T2 enters underneath it.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_out",  "track": "T1", "start_bar": 64, "duration_bars": 8},
  {"type": "fade_in",   "track": "T2", "start_bar": 68, "duration_bars": 8, "from_bar": 0,
   "stems": {"drums": 0.5, "bass": 0.0, "vocals": 0.0, "other": 0.3}},
  {"type": "bass_swap", "track": "T1", "at_bar": 72},
  {"type": "play",      "track": "T2", "at_bar": 76, "from_bar": 8}
]
```

T1 begins fading at bar 64 (fast 8-bar fade). T2 fades in 4 bars later at bar 68, while T1's tail is still decaying. Bass swap clears T1's residual low end at bar 72. T2 at full volume from bar 76. The 4-bar offset means T1 is mostly gone before T2's melody becomes audible.

---

### 8.8 Vocal house → instrumental (mid-kill before vocal entry)

**Situation:** T1 has active vocals in its outro/final chorus. T2 is instrumental. Must kill T1's mids before T2's groove becomes audible — otherwise two pitched layers compete in the 500–2000 Hz range.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 72, "duration_bars": 16, "from_bar": 0,
   "stems": {"drums": 0.7, "bass": 0.0, "vocals": 0.0, "other": 0.3}},
  {"type": "eq",        "track": "T1", "bar": 72, "low": 1.0, "mid": 0.3, "high": 0.9},
  {"type": "bass_swap", "track": "T1", "at_bar": 80, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 88, "from_bar": 16},
  {"type": "fade_out",  "track": "T1", "start_bar": 80, "duration_bars": 16}
]
```

T1 mid EQ cut to 0.3 (≈−9 dB) fires at the same bar T2 starts fading in — T1's vocal recedes before T2's other/pad layer is audible. T2 `stems: other: 0.3` intentionally low during the fade window so T2's harmonic content isn't competing. Bass swap at bar 80 (8-bar mark, phrase boundary). Once T2's full groove fires at bar 88, T1's already mid-cut and fading. T1's `vocals` are gone before T2's groove is at full volume.

---

### 8.9 Techno 64-bar texture blend (atmospherics-first, kick swap mid-blend)

**Situation:** Both tracks are sparse hypnotic/melodic techno, same or adjacent key. Genre permits a 64-bar overlap. Phase 1: T2's atmospherics bleed in while T1's kick holds the floor. Phase 2: hard kick/bass swap at the 32-bar mark. Phase 3: T1's synths fade as T2's groove establishes.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 64, "duration_bars": 32, "from_bar": 0,
   "stems": {"drums": 0.0, "bass": 0.0, "vocals": 0.0, "other": 0.8}},
  {"type": "eq",        "track": "T1", "bar": 80, "low": 1.0, "mid": 0.7, "high": 0.9},
  {"type": "bass_swap", "track": "T1", "at_bar": 96, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 96, "from_bar": 32},
  {"type": "fade_out",  "track": "T1", "start_bar": 96, "duration_bars": 32}
]
```

T2 enters at bar 64 with atmospherics only (`drums: 0.0`) — T1's kick carries the pulse uninterrupted. T1 mid EQ rolls to 0.7 at bar 80 (16 bars in) as T2's synths establish. Hard bass+kick swap at bar 96 (32-bar mark, phrase boundary): T2's full kit and bass take over. T1 fades over the next 32 bars. Total blend: 64 bars. Kick was never doubled.

---

### 8.10 D&B 8-bar precision drop-swap

**Situation:** T1 is D&B nearing its outro/break. T2 is cued near its drop (from_bar=48 = 8 bars before T2's drop at bar 56). Bring T2's drums in during T1's break; bass swap fires exactly when T2's drop hits. High BPM means 8 bars is enough — long blends get cluttered.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 56, "duration_bars": 8, "from_bar": 48,
   "stems": {"drums": 0.7, "bass": 0.0, "vocals": 0.0, "other": 0.0}},
  {"type": "bass_swap", "track": "T1", "at_bar": 64, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 64, "from_bar": 56},
  {"type": "fade_out",  "track": "T1", "start_bar": 56, "duration_bars": 16}
]
```

`from_bar: 48` cues T2 8 bars before its drop so the fade window is the lead-in, not the drop itself. Drums-only fade (`other: 0.0`) — no harmonic content during the handover. Bass swap at bar 64 (T2's drop entry) — the crowd gets T2's sub and full breakbeat as the release moment. T1 fades hard over 16 bars. No melodic overlap.

---

### 8.11 Deliberate −2 energy reset via breakdown bridge

**Situation:** T1 energy=8 (peak). T2 energy=6 (mid-set groove). A raw drop from 8 to 6 reads as "the energy died." Instead: use T1's breakdown as the emotional descent; the crowd has already felt the energy drop before T2's calmer intro begins, so T2 feels like continuation rather than a cliff. EQ T1 down into the breakdown to signal the shift early.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "eq",        "track": "T1", "bar": 48, "low": 0.5, "mid": 0.7, "high": 0.8},
  {"type": "fade_in",   "track": "T2", "start_bar": 56, "duration_bars": 32, "from_bar": 0,
   "stems": {"drums": 0.5, "bass": 0.0, "vocals": 0.0, "other": 0.4}},
  {"type": "bass_swap", "track": "T1", "at_bar": 72, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 88, "from_bar": 32},
  {"type": "fade_out",  "track": "T1", "start_bar": 64, "duration_bars": 24}
]
```

T1 EQ at bar 48 begins the EQ descent 8 bars *before* T2 enters — the sub-bass trim (low=0.5) signals the crowd the energy is ebbing. T2's intro (`other: 0.4`) is intentionally quiet during the 32-bar blend. Bass swap at bar 72 (midpoint of blend). T1 fade_out starts at bar 64 and runs 24 bars. By bar 88 when T2 plays at full, the crowd has accepted the lower energy state via T1's own breakdown arc.

---

### 8.12 BPM jump bridged by loop (>5 BPM gap, breakdown window)

**Situation:** T1 is 134 BPM, T2 is 126 BPM (8 BPM gap). Perform the tempo shift inside a kick-free loop window — absence of kick makes tempo differences imperceptible. Loop T1's sparse breakdown phrase, bring T2 in during the loop.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "loop",      "track": "T1", "start_bar": 64, "loop_bars": 8, "loop_repeats": 2},
  {"type": "fade_in",   "track": "T2", "start_bar": 72, "duration_bars": 16, "from_bar": 0,
   "stems": {"drums": 0.5, "bass": 0.0, "vocals": 0.0, "other": 0.6}},
  {"type": "bass_swap", "track": "T1", "at_bar": 80, "incoming_track": "T2"},
  {"type": "fade_out",  "track": "T1", "start_bar": 80, "duration_bars": 16},
  {"type": "play",      "track": "T2", "at_bar": 88, "from_bar": 16}
]
```

Loop fires at bar 64 on T1's sparse breakdown (no kick). The 16-bar loop window (bars 64–80) is the tempo-transition zone: kick-free music has no rhythmic anchor to expose the BPM mismatch. T2 starts fading in at bar 72 (8 bars into the loop). Bass swap at bar 80 closes the loop and transfers energy to T2. T1 fades over bars 80–96. T2 plays its full groove from bar 88. The loop phase does the perceptual work that an abrupt BPM jump cannot.

---

### 8.13 Psytrance clean bass swap during break (catastrophe prevention)

**Situation:** Both tracks are psytrance with rolling 1/16-note basslines. Overlapping basslines is the worst-sounding outcome in this genre — instant phasing mess. The ONLY safe window is T1's 16-bar break. Bass swap must fire before T1's bassline resumes; T2's bass must not exist until the swap is complete.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 64, "duration_bars": 8, "from_bar": 0,
   "stems": {"drums": 0.5, "bass": 0.0, "vocals": 0.0, "other": 0.7}},
  {"type": "bass_swap", "track": "T1", "at_bar": 64, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 72, "from_bar": 8},
  {"type": "fade_out",  "track": "T1", "start_bar": 64, "duration_bars": 8}
]
```

T1's break starts at bar 64 (bassline and kick stop). Bass swap fires immediately at bar 64 — the downbeat of the break. T2's `bass: 0.0` in fade_in means zero low-end until the swap fires and T2 plays at bar 72. T1 fades hard over 8 bars. The crossover happens entirely inside the break; T1's next bassline cycle never begins. Two rolling basslines never coexist for even 1 bar.

---

### 8.14 Progressive trance breakdown-to-breakdown (same key, 48-bar atmospheric blend)

**Situation:** T1 is in its extended breakdown (drumless, melody + pads only). T2 is queued to its own breakdown start. Same key. This is the longest blend type — the melodic arcs of both tracks interweave before T2's drop gives the emotional release. Only valid with same key or ±1 Camelot.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "fade_in",   "track": "T2", "start_bar": 64, "duration_bars": 48, "from_bar": 0,
   "stems": {"drums": 0.0, "bass": 0.0, "vocals": 0.0, "other": 0.8}},
  {"type": "eq",        "track": "T1", "bar": 80, "low": 1.0, "mid": 0.7, "high": 0.9},
  {"type": "eq",        "track": "T1", "bar": 96, "low": 0.0, "mid": 0.5, "high": 0.7},
  {"type": "bass_swap", "track": "T1", "at_bar": 96, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 112, "from_bar": 48},
  {"type": "fade_out",  "track": "T1", "start_bar": 88, "duration_bars": 32}
]
```

`drums: 0.0` and `bass: 0.0` on T2's fade_in ensures only T2's melodic/pad layer enters — no kick or bassline for the first 48 bars. T1's mid EQ rolls off in two stages (bar 80 → 0.7, bar 96 → 0.5) while T2's pads establish. Bass swap at bar 96 (32-bar mark) clears T1's sub. T1 fade_out runs from bar 88 to 120 — the long tail lets the melodic cross-fade feel organic. T2's drop arrives at bar 112. Both tracks had zero drums for the 48-bar blend window.

---

### 8.15 Emergency short-outro cut (no loop, 4–8 bars of clean material only)

**Situation:** T1 has no usable outro — 8 bars of clean drums then the track ends. Cannot loop (harmonic content makes the repeat obvious). Kill T1's mids/highs immediately, bring T2 in with drums only, cut on the downbeat. This is the damage-limitation path from §3.6.

```json
[
  {"type": "play",      "track": "T1", "at_bar": 0,  "from_bar": 0},
  {"type": "eq",        "track": "T1", "bar": 60, "low": 1.0, "mid": 0.2, "high": 0.4},
  {"type": "fade_in",   "track": "T2", "start_bar": 60, "duration_bars": 8, "from_bar": 0,
   "stems": {"drums": 1.0, "bass": 0.0, "vocals": 0.0, "other": 0.0}},
  {"type": "bass_swap", "track": "T1", "at_bar": 64, "incoming_track": "T2"},
  {"type": "play",      "track": "T2", "at_bar": 68, "from_bar": 8},
  {"type": "fade_out",  "track": "T1", "start_bar": 60, "duration_bars": 8}
]
```

T1 mid/high EQ killed at bar 60 (leaving only sub and kick). T2 enters with drums only (`other: 0.0`, `bass: 0.0`) — zero harmonic overlap during the 8-bar window. Bass swap at bar 64 clears T1's low-end. T2's full groove fires at bar 68. T1 fades out by bar 68. The move is percussive, decisive, and takes only 8 bars. Use this when T1's track structure gives no better option; do not reach for it when a proper outro or loop is available.

---

## 9. AUDIO FEATURE-BASED SECTION DETECTION

> This section describes how an AI should identify section types from computed audio features. Use these rules to validate section labels, resolve ambiguous classifications, and confirm cue point placement.

### 9.1 Decision rules by feature

| Section | RMS | Kick Onsets | Spectral Flux | Chroma Activity | Typical Bar Count |
|---|---|---|---|---|---|
| Intro | Low to Med | Low to Med | Low | Low | 16-32 (techno/trance up to 64) |
| Groove/Verse | Med | High | Med | Med | 16-32 |
| Breakdown | Low | Zero or minimal | Very Low | Low to Med | 8-32 |
| Buildup | Rising | Rising | Rising | Rising | 8-16 |
| Drop/Core | High | Max | High | High | 16-32 (sometimes 48) |
| Outro | Med to Low | High to Low | Med to Low | Low | 16-32 |

**Feature priority for section boundary detection (empirical, ranked):**
1. Energy change (RMS) -- most predictive of valid switch points
2. Harmonic change (chroma novelty) -- second most predictive
3. Timbral change (MFCC shift)
4. Drum onset density change -- lower than musical intuition suggests

**Core section identification -- all three must hold simultaneously:**
1. RMS energy is in the top 40% of the track's dynamic range
2. Bass drum onset density is above the track median
3. RMS is sustained (not declining) for at least 8 bars

### 9.2 Intro and outro detection heuristics

**Intro:** First N bars where bass drum onset density is <50% of track maximum AND spectral content is below 60% of track maximum. N is determined by when both conditions are first violated. Round to nearest 8-bar boundary.

**Outro:** Last M bars (from track end) satisfying the same conditions. Outro additionally shows a consistently declining RMS slope over at least 16 bars. Round to nearest 8-bar boundary.

**Validation:** Both intro and outro durations should be multiples of 8 bars. If computed duration is not a multiple of 8, round to nearest 8-bar boundary.

### 9.3 Boundary detection algorithm (2-stage)

**Stage 1 -- candidate boundaries:**
- Compute RMS in 2-beat (half-bar) windows
- Compute spectral centroid per bar
- Flag any 8-bar boundary where RMS changes >20% between consecutive 8-bar periods as a section boundary candidate
- Flag boundaries where low-frequency energy (20-250 Hz) drops >30% as breakdown candidates
- Flag boundaries where low-frequency energy rises >30% from a low state as drop candidates

**Stage 2 -- alignment to phrase grid:**
- All section boundaries must align to 8-bar multiples of the detected downbeat grid
- EDM section boundaries are always phrase boundaries; a boundary not on the grid is mis-detected
- If a candidate boundary falls within 2 bars of a phrase boundary, snap it to that boundary
- If it falls more than 2 bars from any phrase boundary, discard it as a false positive

### 9.4 Cue point placement from section labels

| Cue Name | Definition | Placement Rule |
|---|---|---|
| `mix_in` | DJ-friendly entry point for T2 | First downbeat of intro (bar 0 of intro section) |
| `breakdown_start` | Optimal T1 exit window | First downbeat of first/main breakdown (sparses section) |
| `drop_bar` | T1 payoff -- DO NOT transition here | First downbeat of first major drop |
| `mix_out` | T1 exit point | First downbeat of outro OR last breakdown start, whichever is later |

All cue bars must be multiples of 8 (phrase-aligned). If computed position is not a multiple of 8, round down to nearest phrase boundary.

---

## 10. FREQUENCY PRECISION REFERENCE

### 10.1 Frequency band map

| Band | Hz Range | DJ EQ | Contains |
|---|---|---|---|
| Sub-bass | 20-80 Hz | Low EQ | Sub-oscillator, kick drum fundamental |
| Bass | 80-250 Hz | Low EQ | Bassline body, kick drum body |
| Low-mid | 250-500 Hz | Mid EQ (low) | Bass harmonic overtones, "mud" zone |
| Mid | 500-2000 Hz | Mid EQ | Vocals (core), chord stabs, snare body |
| High-mid | 2000-4000 Hz | Mid EQ (high) | Vocal presence, synth attack transients |
| Highs | 4000-20000 Hz | High EQ | Hi-hats, cymbals, air, shimmer |

### 10.2 EQ rules during transitions

**Bass band (20-250 Hz):**
- Never run two full bass lines simultaneously. Frequency collision muddies the low end and clips the master.
- Hard kill (on a phrase boundary downbeat) or gradual cut (over 4-8 bars from a phrase boundary) are both valid.
- Cut incoming track's bass to zero BEFORE raising its volume fader. Restore only after outgoing bass is fully removed.
- Two aligned sub-bass notes in the same key at -3dB each is acceptable for up to 2 bars during the swap moment.

**Mid band (250-3000 Hz):**
- Contains vocal, melodic, and harmonic information -- highest clash risk for key incompatibility.
- During blend: reduce outgoing track's mids by 20-40% (equivalent to -2 to -4 dB) to give incoming melody breathing room.
- Never hard-kill mids -- sounds unnatural. Gradual cuts or partial reduction only.
- Cutting mids aggressively also thins the bass sound (250-500 Hz spills upward into mid EQ).

**High band (3000-20000 Hz):**
- Competing hi-hat patterns between two techno tracks are extremely fatiguing.
- Option A: Bring incoming track in on highs first (hats sneak in as extra texture), then introduce mids, then bass.
- Option B: Dip outgoing track's highs while raising incoming track's highs (hi-hat swap mirrors bass swap).
- Allow 2-4 bars of hi-hat overlap -- brief overlap sounds like additional percussion, not a clash.

**Gain staging during transitions:**
- Two channels at full fader + full EQ = guaranteed master bus clipping.
- When both channels are running, reduce both to ~70% fader and bring winner to 100% as loser fades.
- Rule: if master VU is in the red, cut outgoing track's bass first -- it contributes the most RMS per dB.

### 10.3 EQ timing rules

| Action | Timing Constraint |
|---|---|
| Hard bass swap | ONLY on beat 1 of a phrase boundary (bar 1 of 8 or 16-bar section) |
| Gradual bass crossfade | 4-8 bars, must BEGIN on a phrase boundary |
| Hard hi-hat swap | Phrase boundary preferred; 1-2 bar offset acceptable |
| Mid EQ cut | Never cut sharply mid-phrase; always on a phrase boundary |
| High EQ dip | Most forgiving; can begin 2 bars before/after phrase boundary |

---

## 11. CUE POINT STRATEGY

### 11.1 Standard 5-point system

| Slot | Cue Name | Purpose |
|---|---|---|
| 1 | True first beat | Grid reference, clean starts, reliable cue-in |
| 2 | Phrase-in point | First usable mix-in (skips weak/silent intro bars) |
| 3 | Drop / main energy peak | Fast-skip target for drop-swap transitions |
| 4 | Backup re-entry | Alternate entry phrase if first was missed |
| 5 | Outro start / safe mix-out | Signals start of exit window |

### 11.2 Extended 8-point system

Add to the 5-point system:
- Slot 6: Breakdown start (jump target for breakdown-swap technique)
- Slot 7: Post-breakdown re-drop (loop-back target for extending peak energy)
- Slot 8: Percussion-only loop anchor near outro (extend transition window indefinitely)

### 11.3 Cue placement rules

- Set cue on the **actual first beat** of the section -- audio waveforms sometimes show pre-attack transients before the downbeat; the cue goes ON the transient downbeat.
- For tracks with weak intros: skip-ahead cue to first clean 8- or 16-bar phrase that provides useful mixing material.
- A cue should answer a specific transition decision. If it doesn't make a decision faster or more confident, remove it.
- Cue bars must be multiples of 8 (phrase-aligned) -- a cue mid-phrase gives you no useful mix-in point.

### 11.4 BPM/bar-to-seconds reference

| BPM | 8 bars | 16 bars | 32 bars | 64 bars |
|---|---|---|---|---|
| 120 | 16.0s | 32.0s | 64.0s | 128.0s |
| 124 | 15.5s | 30.9s | 61.9s | 123.9s |
| 126 | 15.2s | 30.5s | 61.0s | 122.1s |
| 128 | 15.0s | 30.0s | 60.0s | 120.0s |
| 130 | 14.8s | 29.5s | 59.1s | 118.2s |
| 134 | 14.3s | 28.6s | 57.1s | 114.3s |
| 138 | 13.9s | 27.8s | 55.7s | 111.3s |
| 174 | 11.0s | 22.1s | 44.1s | 88.3s |

---

## 12. ENERGY ARC MANAGEMENT -- NUMBERS

### 12.1 Set phase framework

| Phase | Energy Level | BPM Range | Duration | Primary Techniques |
|---|---|---|---|---|
| Warm-up | 3-5/10 | 110-122 | 45-60 min | Long blends, gentle EQ rides |
| Build | 5-7/10 | 122-128 | 60-90 min | Tighter blends, layered percussion |
| Peak | 8-10/10 | 125-134 | 30-45 min | Short impactful blends, cuts, double drops |
| Release | 6-7/10 | 122-128 | 20-30 min | Breakdown swaps, filter sweeps, echo outs |
| Finale | 4-6/10 | 118-124 | 15-20 min | Extended outros, long blends, loops |

**Opening calibration:** Start at 60-70% of intended peak energy. Preserve 30-40% headroom for the arc. Arriving at max energy on track 1 leaves nowhere to go.

**BPM graduation rule:** Increase BPM by 2-4 BPM per transition for gradual energy build. Maximum safe BPM jump without transition management: <=8 BPM. Above this, a breakdown, loop, or filter bridge is required.

**Peak placement:** In a 90-minute set, peak sits at minutes 55-70 (~2/3 through). In a 60-minute set, minutes 35-45. Plan the peak (3-5 best tracks) first, then build path in and descent out.

### 12.2 Post-peak management

- **Plateau hold:** 2-3 tracks at peak energy but different key/character to sustain without repetition.
- **Controlled dip:** -1 to -2 energy levels for 2-3 tracks, then a second smaller peak. Creates wave shape.
- Never drop more than 2 energy levels per transition when descending -- anything more reads as the set dying, not breathing.

### 12.3 Per-transition energy rules (reinforcement)

- **Default:** +-1 energy level per transition. Imperceptible individually, cumulative across set.
- **Permitted +-2 jumps:** At deliberate set-section boundaries. Limit to 2-4 per hour.
- **Forbidden +-3+ jumps** outside a planned double-drop or set climax.
- **Energy drops (-2) are harder than energy rises (+2).** Always mediate large downward steps via a breakdown, filter sweep, or sparse bridge track. A raw -2 drop reads as "energy died"; a breakdown-mediated -2 reads as "breathing room."

---

## 13. GENRE-SPECIFIC TRANSITION TEMPLATES (DETAILED)

### 13.1 Techno: The texture blend

**Philosophy:** In techno, the kick never stops. Transitions are textural, not structural. You change the atmosphere around the continuous pulse.

**32-64 bar blend sequence:**
1. Two sparse techno tracks can overlap for 32-64 bars without melodic clash (often no melody to clash).
2. Blend sequence: synths/atmospherics fade first (texture shift), then kick swap, then cymbal management.
3. Kick is never doubled -- use crossfader or hard EQ cut (binary, not gradual).
4. Mid-range (synths, atmospherics, noise layers) can coexist -- leave mids open and let textures merge.

**BPM gap management (techno to tech house, ~9 BPM gap):**
Use breakdown of one track as the tempo-adjustment window. Slow pitch fader during A's breakdown (no kick = tempo change less perceptible). Land on new BPM before B's kick drops.

### 13.2 Tech house: The layered groove

**16-32 bar sequence:**
1. Use 16-bar phrase structure as natural mix points.
2. Layer B's percussion first -- loop rolls on A's outro percussion can extend the window.
3. Drop B's bassline after percussion is established and groove is locked in.
4. Cut low-mids on both tracks to prevent mud -- tech house basslines are forward in the 250-500 Hz range.

**Loop roll technique on outro:**
- Engage 2-bar or 4-bar loop roll on A's outro percussion.
- Creates rhythmically exciting texture that masks the incoming track's lower-energy intro.
- Kill loop roll on the same downbeat you bring B's full groove in.

### 13.3 Deep house: Extended atmospheric blend

**32-64+ bar sequence:**
1. Start B on bar 1 of a 32-beat section. Raise B's fader slowly over 30-45 seconds, or snap to 80% on a clean phrase start.
2. Gradually raise B's low-frequency EQ while monitoring master VU. At ~75% of B's bass, begin lowering A's bass.
3. Reduce A's mids more aggressively than highs -- highs contain percussion character; mids contain competing melody.

**Breakdown loop technique (deep house specific):**
1. A's breakdown approaching. Cue a 2-8 bar loop on B's intro (percussive or melodic texture that works as addition).
2. Bring B's loop in during A's breakdown.
3. Engage short loop on A's breakdown melody (2-4 bar loop).
4. Add effects to A's loop (filter, gater, reverb) to progressively de-emphasize it.
5. Disable A's loop, let B play through. B's full groove emerges. A fades out.

### 13.4 Progressive house: The structural blend

**Outro-to-intro alignment:**
- A's outro strips elements every 8 bars back toward percussion-only.
- B's intro adds elements every 8 bars toward full groove.
- These two arcs mirror each other -- aligned, the transition sounds like one continuous composition.
- Overlap window: 16-32 bars.

**Buildup-to-drop sync:**
1. B's buildup (8 bars) aligned with A's final 8 bars of late groove or second drop.
2. B's drop hits on the same beat A's drop would have hit -- crowd gets the expected release from B.
3. Place hot cue on B at 8-bars-before-drop; align with 8 bars remaining in A's current section.

### 13.5 Melodic techno: The arpeggio merge

**Opportunity:** Two tracks sharing the same key with similar arpeggio patterns can produce an extended blend (32-64 bars) where interlocking arpeggios sound like a third, emergent composition.

**EQ strategy:**
- Keys match: leave mids fully open, let arpeggios cascade.
- Keys are adjacent (+-1): suppress B's mids to -2 to -4 dB during transition, bring up gradually as A's melody resolves.
- Keys incompatible: use breakdown swap or filter sweep. Do not attempt a long melodic blend.

**Breakdown usage:** Extended breakdowns (16-32 bars) are emotionally significant in this genre. Use them as transition windows fully -- do not rush through them.

---

## CAVEATS

- **All numeric guidance is a default, not an absolute.** Reading the room -- when audience-feedback signal is available -- overrides any rule above. If the dancefloor is responding strongly to a "wrong" choice, continue.
- **Genre BPM ranges overlap and shift over time.** Treat the ranges as central tendencies; individual tracks may sit outside them.
- **The Camelot Wheel is a heuristic** built on equal-tempered Western tonality. Tracks with modal ambiguity (atonal techno, drone-based tracks, key-shifting productions) may show "compatible" on the wheel but still clash; trust the audio over the metadata.
- **Key-detection algorithms are imperfect** (often 80-95% accurate). Cross-validate with audio analysis when possible; one wrong key tag will produce a wrong-sounding "compatible" mix.
- **The "energy level" 1-10 scale is subjective** but stable within a single library if rated consistently. Different rating sources are not directly comparable.
- **Stem separation introduces artifacts.** Vocal stems especially can have residual instrumentation. Stem-layered transitions sound best when the source mix is dense; sparse mixes expose stem-separation artifacts.
- **The drop-into-drop / double-drop rule of "rare in trance / prog house"** is convention; some modern productions are designed for it. Adjust per artist/label catalog knowledge if available.