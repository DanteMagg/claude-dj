# Claude DJ — Project Brief

## What We're Building

A CLI tool where Claude acts as the creative director of a DJ mix. Give it a folder of local audio tracks; it analyzes them, reasons about how they fit together, and renders an output audio mix.

Claude doesn't touch audio directly. It reads structured analysis data and outputs a **mix script** — a timestamped JSON instruction set — which pydub then executes into actual audio.

The core novelty: Claude decides *where* to transition (anywhere mid-track, not just outros), which stems to layer across tracks, and why. This is creative judgment, not DSP.

---

## Stack

| Tool | Role |
|---|---|
| `allin1` (mir-aidj/all-in-one) | Beats, downbeats, labeled section detection |
| `librosa` | Key estimation (chroma), per-bar RMS energy |
| `demucs` (htdemucs model) | Stem separation + per-stem RMS |
| `anthropic` SDK | Claude as DJ brain — authors mix script |
| `pydub` | Executes mix script → rendered audio file |
| `click` | CLI interface |

---

## Environment

**Pin Python to 3.10.** `allin1` depends on `madmom`, which has known install issues on Python 3.11+. Do this before anything else.

```bash
pyenv install 3.10.13
pyenv local 3.10.13

pip install allin1 demucs librosa pydub anthropic click
```

If `allin1`/`madmom` install fails: fallback to `librosa.beat.beat_track` for beats and `msaf` for segmentation. Document this as a known limitation — labels will be unlabeled boundary clusters (A/B/C) rather than named sections (intro/drop/outro).

---

## Project Structure

```
claude-dj/
├── cli.py              # click entrypoint
├── analyze.py          # full audio analysis pipeline per track
├── mix_director.py     # Claude API call → mix script JSON
├── executor.py         # pydub: mix script → output audio
├── schema.py           # dataclasses/TypedDicts for all data shapes
├── cache/              # stems + analysis JSON cached per track (by file hash)
├── outputs/            # rendered mix audio
└── README.md
```

Cache by file hash so stems and analysis only run once per track — Demucs on CPU is slow (10–20 min per track first run).

---

## Track Analysis Schema

Everything the analysis pipeline builds per track. This is the payload sent to Claude. Target: **800–1500 tokens per track**, so a 5–10 track set fits comfortably in one Claude call.

```json
{
  "id": "T1",
  "title": "Track Name",
  "artist": "Artist",
  "file": "path/to/track.mp3",
  "duration_s": 245.7,
  "bpm": 128.0,
  "first_downbeat_s": 0.33,
  "key": {
    "camelot": "8A",
    "standard": "Am",
    "mode": "minor",
    "tonic": "A"
  },
  "energy_overall": 7,
  "loudness_lufs": -9.2,
  "bar_grid": {
    "n_bars": 128,
    "beats_per_bar": 4
  },
  "energy_curve_per_bar": "11233456678765432112345677...",
  "sections": [
    {
      "label": "intro",
      "start_bar": 0,
      "end_bar": 16,
      "start_s": 0.33,
      "end_s": 30.5,
      "energy": 3,
      "loudness_dbfs": -18.2,
      "stems": {
        "drums":  { "presence": 4, "rms_db": -18.1 },
        "bass":   { "presence": 2, "rms_db": -24.4 },
        "vocals": { "presence": 0, "rms_db": -45.0 },
        "other":  { "presence": 5, "rms_db": -14.3 }
      }
    },
    {
      "label": "drop",
      "start_bar": 32,
      "end_bar": 64,
      "start_s": 62.1,
      "end_s": 123.8,
      "energy": 9,
      "loudness_dbfs": -7.2,
      "stems": {
        "drums":  { "presence": 9, "rms_db": -8.1 },
        "bass":   { "presence": 8, "rms_db": -10.4 },
        "vocals": { "presence": 0, "rms_db": -45.0 },
        "other":  { "presence": 7, "rms_db": -12.3 }
      }
    }
  ],
  "cue_points": [
    { "name": "mix_in",  "bar": 16, "type": "phrase_start" },
    { "name": "mix_out", "bar": 112, "type": "outro_start" }
  ],
  "stems": {
    "vocals": "cache/T1_vocals.wav",
    "drums":  "cache/T1_drums.wav",
    "bass":   "cache/T1_bass.wav",
    "other":  "cache/T1_other.wav"
  }
}
```

### Key implementation notes

**energy_curve_per_bar**: one digit 0–9 per bar, downbeat-aligned, computed from librosa RMS aggregated between downbeat timestamps from `allin1`. For a 4-min track at 128 BPM this is ~128 chars (~50 tokens). Do not use per-beat or per-4-second windows — they don't align with bars and the LLM reasons in bar units.

**stems.presence**: 0–10 integer, quantized from per-stem RMS normalized to the loudest section of that stem across the track. Apply a silence threshold: anything below –30 dBFS treat as 0 presence. Demucs produces ghost artifacts (e.g., faint "vocals" on instrumental tracks) — without this threshold Claude will hallucinate stem layers that don't meaningfully exist.

**key**: always pass both Camelot and standard notation. Claude has seen music theory text (Am, C major, relative minor) far more than Camelot during training, but Camelot is the DJ-native notation for harmonic compatibility reasoning (adjacent numbers = compatible keys). Give it both.

**sections**: sourced from `allin1` output. Expected labels: `intro`, `verse`, `chorus`, `bridge`, `outro`, `start`, `end`. For EDM, remap `chorus` → `drop` when section energy is ≥8 and drums presence is ≥8. `allin1` is trained on Western pop and may mislabel on niche EDM genres — expose raw boundary times alongside labels so Claude can sanity-check using the energy curve.

---

## Analysis Pipeline (`analyze.py`)

Run in this order per track:

1. **Demucs** — separate stems first. `htdemucs` model, outputs 4 stems: vocals/drums/bass/other. Cache to `cache/{track_hash}/`.
2. **allin1** — run on the full mix (not stems) for beats, downbeats, and section labels. Feed it the original file path. Returns `beats`, `downbeats`, `beat_positions` (bar-relative), `segments` (list of `{start, end, label}`).
3. **librosa** — load audio, compute:
   - `librosa.feature.chroma_cqt` → Krumhansl-Schmuckler key estimation
   - Per-bar RMS: compute `librosa.feature.rms` then aggregate frame-level values between consecutive downbeat timestamps from step 2
4. **Per-stem RMS** — load each Demucs stem wav, compute mean RMS per section using section timestamps from step 2
5. **Serialize** — assemble the track schema above, write to `cache/{track_hash}/analysis.json`

---

## Mix Script Schema

What Claude outputs. The executor converts this to audio.

```json
{
  "mix_title": "Claude DJ Set — 2026-04-29",
  "reasoning": "Brief explanation of transition decisions",
  "tracks": [
    { "id": "T1", "path": "path/to/track1.mp3", "bpm": 128.0, "first_downbeat_s": 0.33 },
    { "id": "T2", "path": "path/to/track2.mp3", "bpm": 124.0, "first_downbeat_s": 0.12 }
  ],
  "actions": [
    { "type": "play",     "track": "T1", "at_bar": 0,   "from_bar": 0 },
    { "type": "fade_in",  "track": "T2", "start_bar": 80, "duration_bars": 16,
      "stems": { "drums": 1.0, "bass": 0.0, "vocals": 0.0, "other": 0.8 } },
    { "type": "eq",       "track": "T1", "bar": 88,
      "low": 0.0, "mid": 0.8, "high": 1.0 },
    { "type": "fade_out", "track": "T1", "start_bar": 88, "duration_bars": 16 },
    { "type": "play",     "track": "T2", "at_bar": 96,  "from_bar": 0 }
  ]
}
```

### Action types

| Action | Required fields | Notes |
|---|---|---|
| `play` | `track`, `at_bar`, `from_bar` | `from_bar` = where in the source track to start playback |
| `fade_in` | `track`, `start_bar`, `duration_bars` | Optional `stems` dict (0.0–1.0 per stem) for stem-selective intro |
| `fade_out` | `track`, `start_bar`, `duration_bars` | Full mix fade unless stems specified |
| `eq` | `track`, `bar`, `low`, `mid`, `high` | 0.0–1.0 gain per band. Approximated in pydub via low/high pass filters |

### Timeline unit

**Everything is in bars.** The executor converts at runtime:

```python
def bars_to_ms(bars: float, bpm: float) -> int:
    return int(bars * 4 * 60_000 / bpm)
```

Never use seconds in the mix script — it breaks on any BPM mismatch and fights the beatgrid.

---

## Claude Prompt Design (`mix_director.py`)

### System prompt (paraphrased intent — implement in full)

```
You are a professional DJ and music producer. You will be given structured analysis 
data for a set of tracks and must author a mix script as JSON.

Your job:
- Choose transition points anywhere mid-track (not just outros) where energy, 
  frequency space, or rhythm creates a natural opening
- Use stem-level information to decide what to layer before a full transition
- Reason about harmonic compatibility using Camelot key notation (±1 = compatible, 
  same number = relative major/minor)
- Keep energy arc coherent across the full set
- Output ONLY valid JSON matching the mix script schema. No prose outside the JSON.
  Include your reasoning in the "reasoning" field.

Rules:
- Transitions must land on downbeats (bar boundaries)
- Crossfades should be 8–32 bars depending on energy match
- Never transition into a drop — transition into an intro or breakdown, 
  let the drop hit naturally
- If key compatibility is poor (>2 steps on Camelot wheel), note this in reasoning 
  and compensate with a quick transition or energy bridge
```

### User message structure

```
Here are {n} tracks to mix. Analyze the set and output a mix script.

TRACKS:
{json.dumps(track_analyses, indent=2)}

Output the mix script JSON now.
```

### API call

```python
response = anthropic.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=4096,
    messages=[
        {"role": "user", "content": user_message}
    ],
    system=system_prompt
)
mix_script = json.loads(response.content[0].text)
```

---

## Executor (`executor.py`)

pydub implementation notes:

- Load each track as `AudioSegment`
- Time-stretch to match BPMs before mixing: use `pydub.effects` or shell out to `rubberband` CLI for better quality time-stretching
- `fade_in`/`fade_out` → `AudioSegment.fade_in(ms)` / `.fade_out(ms)`
- Stem-selective fade: load individual stem wavs, apply fade to each, recombine with `overlay` before crossfading with the outgoing track
- EQ approximation: pydub has `low_pass_filter` and `high_pass_filter` — use them to simulate killing lows/highs. True mid-band EQ requires numpy/scipy bandpass filter; implement if needed
- Output: export as WAV first (lossless), offer MP3 export as optional flag

---

## CLI (`cli.py`)

```
Usage: claude-dj mix [OPTIONS] TRACKS_DIR

Options:
  --output PATH       Output file path [default: outputs/mix_{timestamp}.wav]
  --analyze-only      Run analysis pipeline only, skip Claude + render
  --script PATH       Use existing mix script JSON, skip analysis + Claude
  --model TEXT        Claude model to use [default: claude-sonnet-4-5]
  --help
```

---

## Known Limitations & Gotchas

**madmom / Python 3.10**: allin1 requires madmom. madmom has install issues on Python ≥3.11. Pin to 3.10 before starting.

**Demucs CPU time**: htdemucs takes 10–20 min per track on CPU. Cache aggressively by file hash. Consider adding a `--no-stems` flag that skips Demucs and uses full-mix energy only (degrades stem-fade capability but much faster for testing).

**Ghost stem artifacts**: Demucs produces faint bleed on stems (e.g., instrumental tracks with –35 dB "vocals"). Silence threshold: treat any stem with mean RMS below –30 dBFS as absent (presence = 0). Implement this in the analysis step, not at prompt time.

**allin1 EDM label accuracy**: trained on Western pop. May label drops as "chorus". Post-process: if a section has energy ≥8 AND drums presence ≥8, relabel to "drop" regardless of allin1 output.

**Camelot key accuracy**: librosa chroma key estimation is ~85–95% on clean pop/electronic but degrades on complex harmonic content or noisy recordings. Surface confidence score in the schema if available; prompt Claude to note when key confidence is low.

**pydub time-stretching**: pydub has no native time-stretch. For BPM matching between tracks, shell out to `rubberband-cli` (`pip install pyrubberband`). Without this, crossfades between tracks at different BPMs will have beat drift.

**Token budget**: ~800–1500 tokens per track. At 10 tracks that's ~10–15K input tokens, well within Claude's context. If sets grow larger (20+ tracks), chunk into overlapping groups of 8–10 and stitch mix scripts.

---

## Suggested Build Order

1. `schema.py` — define all dataclasses first so everything else has types to import
2. `analyze.py` — get one track fully analyzed and cached before touching Claude
3. `mix_director.py` — test Claude output with hardcoded analysis JSON before wiring to analyzer
4. `executor.py` — test with a hardcoded simple mix script (2 tracks, basic crossfade) before Claude-generated scripts
5. `cli.py` — wire everything together last

Test each layer in isolation. The analysis pipeline is the most failure-prone part (madmom install, Demucs memory, allin1 label accuracy) — get it stable before building on top of it.
