# AI DJ System — Mixing Skill

> Rules for mixing 4/4, phrase-based electronic dance music. Prescriptive defaults — override only when explicit conditions are met.

---

## 0. CRITICAL RULES

Violations are audibly bad. No exceptions.

1. **Never run two basslines simultaneously.** Kill incoming low EQ to −∞ before raising its fader. Bass swap is instantaneous on a phrase boundary.
2. **Never run two lead vocals simultaneously** for more than 2 bars unless keys are identical or relative (nA↔nB).
3. **All transitions start on a phrase boundary** — 16- or 32-bar boundary preferred.
4. **Default harmonic moves (Camelot):** same key, ±1 on the wheel, or A↔B at the same number. All safe.
5. **BPM tolerance:** ±4 BPM max for long blends. Beyond that, use a bridge track or breakdown to mask the shift.
6. **Default transition:** outgoing OUTRO over incoming INTRO. Never mix into a drop. Never mix out of an intro.
7. **Bass swap timing:** kill outgoing low EQ on the downbeat where incoming bassline enters — not before, not after.
8. **Energy step rule:** ±1 per transition by default. ±2 only at planned peak/reset moments. Never ±3.
9. **Double drop is a deliberate set-piece**, not a default.
10. **When in doubt:** mix during a drum-only / percussion-only window.

---

## 1. HARMONIC MIXING (CAMELOT)

### Compatible moves from any key `nX`

| Move | Operation | Energy effect | Use freely? |
|---|---|---|---|
| Same key | `nX → nX` | Neutral | YES |
| Perfect fifth up | `nX → (n+1)X` | Slight lift | YES |
| Perfect fifth down | `nX → (n−1)X` | Slight relax | YES |
| Relative major/minor | `nA ↔ nB` | Mood shift, no pitch clash | YES |
| Diagonal | `nA → (n+1)B` | Subtle color shift | YES with care |
| +2 number, same letter | `nX → (n+2)X` | Strong lift | OCCASIONAL — ≤16-bar overlap only |
| +7 number (≡ −5) | `nX → (n+7)X` | Modulation lift | OCCASIONAL — short blends only |

Wrap-around: Camelot numbers mod 12. `12+1=1`, `1−1=12`.

**Distance penalty:** Beyond 2 numeric steps same letter = effectively unrelated. Do NOT attempt a melodic blend.

### Breaking the rules

Only under these conditions:
1. Short overlap (≤8 bars) — no time to register the dissonance.
2. Mix during a percussion-only section of one or both tracks.
3. Cut outgoing mids (200 Hz–5 kHz) during overlap — hides key-defining content.
4. Intentional +2 semitone energy boost — use ≤1 per 30 minutes.
5. Use a percussion bridge track between incompatible tracks.

### Vocal handling

- **Two vocals never overlap >2 bars** unless keys are identical or nA↔nB.
- Cut outgoing mids by ≥6 dB before incoming vocal enters.
- Acapella over instrumental: same key or ±1 only. No exceptions for long blends.

---

## 3. TRANSITION TECHNIQUES

### 3.1 Bass swap protocol

1. **T−16:** incoming low EQ at full kill. Mid and high at unity.
2. **T−16 to T−4:** raise incoming fader to full.
3. **T=boundary downbeat:** simultaneously kill outgoing low + restore incoming low. One motion.
4. **T+8 to T+16:** reduce outgoing mid by 6–12 dB (gradual, not full-kill).
5. **T+16 to T+32:** reduce outgoing high gradually (≥4 bars).
6. **T+32:** outgoing fader down.

**Order:** lows swap first (instant), mids second (gradual), highs last (most gradual).

### 3.2 Stem layering order (incoming track)

1. Drums / hi-hats first (no harmonic content)
2. Atmospheric / pads / other
3. Bass — only at bass swap downbeat
4. Vocals / lead — last, only after bass swap complete and outgoing vocal ended

Outgoing track: reverse order (vocals first, other, bass at swap, drums last).

### 3.3 Crossfade length defaults

| Context | Overlap |
|---|---|
| Deep house, ambient | 48–64 bars |
| Progressive house, melodic techno | 32–48 bars |
| Tech house, techno, house | 16–32 bars |
| Uplifting trance, EDM | 16 bars |
| D&B, fast cuts | 8 bars |
| Cut / energy boost | 1–4 bars |

Longer overlap = stricter harmonic requirement. 64-bar blend requires same key, ±1, or A↔B.

### 3.4 Energy dip technique

Best transition windows (priority order):
1. Outgoing OUTRO (last 16–32 bars)
2. Outgoing secondary breakdown
3. Outgoing final-chorus tail
4. Outgoing intro tail (emergency only)

**Avoid:** drops, build-ups/risers, first 8 bars of any new section.

### 3.5 Double-drop rules

1. Same BPM within 0.1 BPM — no exceptions.
2. Harmonically compatible (same key, ±1, or A↔B).
3. One track must be sonically simpler at the drop.
4. No bass swap — so one track must have non-melodic or cut sub.
5. Phrase alignment mandatory: drops on bar 1 of both drop sections, same downbeat.
6. Native to D&B and EDM. Avoid in deep house, prog house, trance.
7. ≤2–3 per hour.

### 3.6 Damage limitation (incompatible keys)

1. Shorten overlap to ≤8 bars.
2. Mix during percussion-only window.
3. Cut outgoing mids by 12 dB during overlap.
4. HPF sweep on outgoing (filter to ~500 Hz, removes harmonic content).
5. Use a one-shot FX wash (~1 bar) to mask the swap moment.
6. Cut, don't blend — clean instant cut on downbeat is better than 16 bars of clash.
7. Bridge with a percussion tool track.

---

## 6. OPERATIONAL CHECKLIST (per transition)

Resolve in order before executing:

1. **Phrase position:** transition aligned to 16- or 32-bar boundary in BOTH tracks?
2. **BPM:** |ΔBPM| ≤ 4 (or half/double-time relationship)?
3. **Key:** move on safe set (same / ±1 / A↔B / diagonal)?
4. **Section:** outgoing in outro/breakdown AND incoming in intro?
5. **Energy step:** ΔEnergy ≤ ±1 (or justified ±2)?
6. **Vocal collision:** two vocals overlap >2 bars?
7. **Bass swap:** clear downbeat for swap inside overlap window?
8. **Crossfade length:** per genre table §3.3.
9. **Stem order:** drums → other → bass(swap) → vocals.
10. **Execute.**

Fallback when any check fails: **8-bar percussion-window cut** (universal damage-limitation).

---

## 7. LOOP TECHNIQUE

### Legitimate uses

**Use 1 — Extend short outro:** T1 outro too short (≤8 bars clean). Loop last drum-only phrase to create transition runway.

**Use 2 — Hold a peak moment:** Floor responding strongly to a drop. Loop the drop's first 8-bar phrase for 1–2 repeats to extend peak before transitioning.

**Use 3 — Pre-drop tension:** Loop last 8 bars of a build (1 repeat only) to amplify anticipation.

### Two loop strategies

**Strategy A — loop T1 to buy runway:**
Loop a clean section of T1 to extend its playtime while T2 fades in underneath.
Use when T1's exit zone is short or the mix-out cue arrives before T2 is ready.

**Strategy B — fade in a T2 loop:**
Start T2 as a looped texture while fading it in. T2 enters as a repeated phrase
(minimal, rhythmic), builds presence over the loop repeats, then breaks the loop and
plays freely. The loop break is the "moment" — T2 snaps into full mix.
Pattern:
```
eq(T2, bar=<fade_start>, low=0.0)
loop(T2, start_bar=<fade_start>, loop_bars=4, loop_repeats=3)
fade_in(T2, start_bar=<fade_start>, duration_bars=12, from_bar=<T2_loop_bar>)
bass_swap(T1, at_bar=<fade_start+8>, incoming_track=T2)
eq(T2, bar=<fade_start+8>, low=1.0)
fade_out(T1, start_bar=<fade_start>, duration_bars=12)
play(T2, at_bar=<fade_start+12>, from_bar=<T2_loop_bar+12>)
```
The `play(T2)` after fade_in completion breaks the loop — T2 resumes from where it
would be without the loop (`from_bar + duration_bars`).

### Never loop

- Active vocal phrases (`vocals > 0.20` in zone data)
- Intro sections (loop of unresolved material = dead end)

### Technical rules

1. `start_bar` for T1 loops must be a bar with `drums > 0.25` and `vocals < 0.20`.
2. For T2 loops: use a T2 section available in T2's loop candidates (zone hints show these).
3. Valid `loop_bars` values: 2, 4, 8, 16. (4 = tech house short loop; 8 = standard house)
4. `loop_repeats` 1–4. One = standard. Beyond four loses the effect.
5. After loop: track resumes from `start_bar + loop_bars * loop_repeats`. Plan accordingly.
6. Do NOT place `loop` and `fade_out` at the same bar for the same track.
7. One loop per transition maximum (either T1 or T2, not both).

---

## 14. ACTION REFERENCE

### 14.1 `play`

Starts full audio mix at `at_bar`, from source bar `from_bar`.

```json
{"type": "play", "track": "T1", "at_bar": 0, "from_bar": 0}
```

- T2 `play` fires at `fade_in.start_bar + duration_bars`, `from_bar = fade_in.from_bar + duration_bars`.
- Skip silent intro bars: set `from_bar` to first bar where `drums > 0.15` or `harmonic > 0.1`.

### 14.2 `fade_out`

Linear gain 1.0→0.0 over `duration_bars`. Track is silent from `start_bar + duration_bars` onward.

```json
{"type": "fade_out", "track": "T1", "start_bar": 72, "duration_bars": 16}
```

- `start_bar`: bar where T1 zone shows `rms` dropping below 0.35 or section = OUTRO/BREAKDOWN.
- **MANDATORY for every non-final track.** Missing = normalizer injects one in the wrong place.

### 14.3 `fade_in`

Brings T2 into the mix over `duration_bars` with per-stem volume control.

```json
{
  "type": "fade_in",
  "track": "T2",
  "start_bar": 72,
  "duration_bars": 16,
  "from_bar": 8,
  "stems": {"drums": 0.8, "bass": 0.0, "other": 0.6}
}
```

- **`stems` is the primary T2 entry mechanism** — always include it on blend transitions.
  - `drums`: 0.7–0.9 — kick/hi-hat arrives first to lock rhythm.
  - `bass`: **always 0.0** — bass handover happens at `bass_swap`, not here.
  - `other`: 0.5–0.7 — pads/atmosphere underneath.
  - Omit `vocals` key to keep T2 lead vocal absent until after bass swap.
- `from_bar`: first T2 bar where `drums > 0.15` (use zone data — kick must be present).
- Stems let T2 enter as rhythm + texture only, no clashing bass or vocals.

### 14.4 `bass_swap`

Removes T1 bass and releases T2 bass. Instantaneous at a single bar. `incoming_track` is **required**.

```json
{"type": "bass_swap", "track": "T1", "at_bar": 80, "incoming_track": "T2"}
```

- `at_bar` must be a multiple of 8.
- Default position: midpoint of fade window (~50%). Concept directives may specify early (25%) or late (75%).
- Mandatory on every blend and drop_swap transition.

### 14.5 `eq`

Sets frequency band volumes at a specific bar. Supports smooth ramping via `eq_duration_bars`.

```json
{"type": "eq", "track": "T1", "bar": 72, "low": 0.0, "mid": 0.5, "high": 1.0}
```

With smooth ramp (like turning a knob over 4 bars):
```json
{"type": "eq", "track": "T1", "bar": 72, "low": 0.0, "mid": 0.5, "high": 1.0, "eq_duration_bars": 4}
```

- `low`: 0.0=kill bass, 1.0=unity. Never run two tracks with `low > 0.5` simultaneously.
- `mid`: attenuation for harmonic/vocal clash management.
- `high`: hi-hat management. Rarely needed.
- `eq_duration_bars`: if set, the EQ ramps linearly from current value to target over this many bars — **use this for smooth DJ-style knob turns**. Without it, eq snaps instantly.
- **PERSISTENT** — holds until explicitly restored.
- Every non-unity `eq` on T1 during a blend does NOT need restore — T1 is fading out.

Standard pre-cut (every blend — ramp over 4 bars for smoothness):
```json
{"type": "eq", "track": "T1", "bar": <fade_in.start_bar - 8>, "low": 0.0, "mid": 1.0, "high": 1.0, "eq_duration_bars": 4}
```

### 14.5b `gain`

Independent channel volume (0–1), separate from EQ. Supports ramping.

```json
{"type": "gain", "track": "T1", "at_bar": 80, "volume": 0.6, "duration_bars": 8}
```

- `volume`: 0.0=silence, 1.0=unity (default). Values between 0 and 1 attenuate.
- `duration_bars`: ramp duration. Without it, volume snaps instantly.
- Use when you need subtle level riding — e.g. gently duck T1 as T2's energy builds.
- Combine with `fade_out` for a pre-fade gain reduction before the actual fade.

### 14.6 `loop`

Repeats a phrase `loop_repeats` times, then resumes from `start_bar + loop_bars * loop_repeats`.

```json
{"type": "loop", "track": "T1", "start_bar": 64, "loop_bars": 8, "loop_repeats": 2}
```

- `start_bar`: multiple of 8.
- `loop_bars`: 2, 4, 8, or 16.
- After loop: emit `fade_out` at the resume point, not the loop start.

### 14.7 Cut transition

```json
[
  {"type": "fade_out", "track": "T1", "start_bar": 72, "duration_bars": 4},
  {"type": "play",     "track": "T2", "at_bar": 76, "from_bar": 0}
]
```

Use when: Camelot distance ≥ 3, or T1 near-silent, or energy shift is deliberately dramatic.

### 14.8 Drop swap (`style: "drop_swap"`)

```json
[
  {"type": "fade_in",   "track": "T2", "start_bar": 60, "duration_bars": 8, "from_bar": 0},
  {"type": "bass_swap", "track": "T1", "at_bar": 64, "incoming_track": "T2"},
  {"type": "fade_out",  "track": "T1", "start_bar": 60, "duration_bars": 8},
  {"type": "play",      "track": "T2", "at_bar": 68, "from_bar": 8}
]
```

`duration_bars: 8`, T2 drums at full from bar 1, bass_swap at midpoint.

### 14.9 Transition selection (zone data → technique)

```
T1 exit rms < 0.20 → BLEND (16-bar, standard bass_swap)
T1 exit rms 0.20–0.55, bars remaining ≥ 24 → BLEND
T1 exit rms 0.20–0.55, bars remaining < 16 → LOOP then BLEND
T1 exit rms > 0.55, T2 also at DROP → DROP SWAP
T1 exit rms > 0.55, T2 has clean intro → LOOP peak hold then BLEND
Camelot ≥ 3 → CUT or SHORT BLEND (8 bars, cut mids)
```

### 14.10 Diversity requirement

Do not output the same action sequence on consecutive transitions. Vary: overlap length (8/16/24/32), technique type (blend/loop-blend/cut), bass_swap position.
