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

## CAVEATS

- **All numeric guidance is a default, not an absolute.** Reading the room — when audience-feedback signal is available — overrides any rule above. If the dancefloor is responding strongly to a "wrong" choice, continue.
- **Genre BPM ranges overlap and shift over time.** Treat the ranges as central tendencies; individual tracks may sit outside them.
- **The Camelot Wheel is a heuristic** built on equal-tempered Western tonality. Tracks with modal ambiguity (atonal techno, drone-based tracks, key-shifting productions) may show "compatible" on the wheel but still clash; trust the audio over the metadata.
- **Key-detection algorithms are imperfect** (often 80–95% accurate). Cross-validate with audio analysis when possible; one wrong key tag will produce a wrong-sounding "compatible" mix.
- **The "energy level" 1–10 scale is subjective** but stable within a single library if rated consistently. Different rating sources are not directly comparable.
- **Stem separation introduces artifacts.** Vocal stems especially can have residual instrumentation. Stem-layered transitions sound best when the source mix is dense; sparse mixes expose stem-separation artifacts.
- **The drop-into-drop / double-drop rule of "rare in trance / prog house"** is convention; some modern productions are designed for it. Adjust per artist/label catalog knowledge if available.