# Claude DJ Backend Overhaul — Design Spec
_2026-04-30_

## Overview

Full refactor of the Python backend. The core audio engine works; the goal is to make it maintainable and fix the audio quality issues that cause harsh transitions. `server.py` (1024 lines, does everything) is split into focused modules. All in-process state moves from plain dicts to typed dataclasses. Seven DSP improvements land in `executor.py`. Legacy endpoints are removed. Tests cover the two hardest-to-debug areas: the normalizer safety layer and the audio DSP.

---

## Design Decisions

| Dimension | Decision | Rationale |
|---|---|---|
| Architecture | Split server.py into library.py + dj_session.py + state.py | Single responsibility; routes become 8-line handlers |
| State | Typed dataclasses (stdlib) not Pydantic | Already using dataclasses throughout; no new dependency |
| Legacy endpoints | Delete /api/analyze, /api/analyze/{job_id}, /api/plan | Frontend only uses /api/dj/*; dead code is a maintenance burden |
| DSP | Equal-power crossfades, soft limiter, loudness matching, smooth bass swap, loop crossfade, render parity, EQ shelving | All audibly fix the "glitchy/harsh" transition problem |
| Tests | pytest, synthetic AudioSegment (no real tracks), temp dirs | Fast, no external dependencies, numerical assertions on DSP properties |
| DI | Library + stores passed as FastAPI Depends() | Worker receives deps as args instead of closing over globals — testable |

---

## File Structure

```
claude-dj/
├── server.py          # Routes only (~200 lines). No business logic.
├── state.py           # NEW — typed dataclasses for all in-process state
├── library.py         # NEW — Library class: load/save/scan/lookup/atomic write
├── dj_session.py      # NEW — DjSessionStore + dj_worker + helpers
├── schema.py          # Unchanged
├── analyze.py         # Unchanged
├── mix_director.py    # Unchanged
├── audio_queue.py     # Unchanged
├── executor.py        # 7 DSP improvements
├── normalizer.py      # Unchanged
└── tests/
    ├── test_normalizer.py
    ├── test_executor.py
    ├── test_library.py
    └── test_dsp.py
```

---

## State Models (`state.py`)

Replaces five plain dict stores (`_library`, `_sessions`, `_scan_jobs`, `_dj_sessions`, `_analyze_jobs`). Every field that was implicit becomes explicit. Attribute access replaces string key access — typos become `AttributeError` at the access site rather than silent `None` propagation.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal

@dataclass
class LibraryEntry:
    hash: str
    path: str
    title: str
    artist: str
    bpm: float
    key_camelot: str
    key_standard: str
    energy: int
    duration_s: float
    energy_curve: str
    cue_points: list[dict]
    first_downbeat_s: float
    analyzed_at: str
    loudness_dbfs: float = -14.0   # used for loudness matching

@dataclass
class ScanJob:
    scan_id: str
    status: Literal["running", "done", "error"]
    progress: int = 0
    total: int = 0
    known: int = 0
    new: int = 0
    skipped: int = 0
    error: Optional[str] = None

@dataclass
class DjDeckA:
    track_id: str
    hash: str
    title: str
    start_bar: int
    status: str = "playing"

@dataclass
class DjDeckB:
    status: Literal["starting", "analyzing", "planning", "loading", "ready"]
    title: str

@dataclass
class DjSessionState:
    dj_id: str
    status: Literal["starting", "playing", "stopped", "error"]
    model: str
    let_claude_pick: bool
    pool: list[str]
    queue: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    deck_a: Optional[DjDeckA] = None
    deck_b: Optional[DjDeckB] = None
    track_counter: int = 0
    current_start_bar: int = 0
    ref_bpm: Optional[float] = None
    error: Optional[str] = None

@dataclass
class AudioSession:
    session_id: str
    status: Literal["loading", "ready", "error"]
    script: object          # MixScript — typed as object to avoid circular import
    ref_bpm: float
    tracks: list[dict]
    load_progress: int = 0
    load_total: int = 0
    scheduler: Optional[object] = None   # ChunkScheduler
    error: Optional[str] = None
```

**Stores** — thin wrappers that enforce typed access:

```python
class ScanJobStore:
    def create(self, scan_id: str) -> ScanJob: ...
    def get(self, scan_id: str) -> Optional[ScanJob]: ...

class AudioSessionStore:
    def create(self, session_id: str, sess: AudioSession) -> None: ...
    def get(self, session_id: str) -> Optional[AudioSession]: ...

class DjSessionStore:
    def create(self, dj_id: str, state: DjSessionState) -> None: ...
    def get(self, dj_id: str) -> Optional[DjSessionState]: ...
```

---

## Library Module (`library.py`)

Owns the persistent track store. One instance created at startup, injected via `Depends()`.

```python
class Library:
    def __init__(self, cache_dir: Path) -> None: ...

    def load(self) -> None:
        # reads library.json; starts empty (no crash) if file missing

    def save(self) -> None:
        # atomic: write to library.json.tmp then os.rename() → survives mid-write crash

    def get(self, hash: str) -> Optional[LibraryEntry]: ...
    def get_all(self) -> list[LibraryEntry]:
        # sorted by (artist.lower(), title.lower())

    def upsert(self, hash: str, entry: LibraryEntry) -> None:
        # add or update, then save()

    def resolve(self, val: str) -> Optional[str]:
        # val is hash → return it if present
        # val is path → find matching entry, return hash
        # returns None if not found

    def to_analysis(self, hash: str, track_id: str) -> TrackAnalysis:
        # builds TrackAnalysis from LibraryEntry
        # replaces _analysis_from_entry in server.py
```

**Scan job** stays an async background task but calls `library.upsert()` instead of mutating `_library` directly. `ScanJobStore` holds the in-flight jobs.

---

## DJ Session Module (`dj_session.py`)

The `_dj_worker` and all helpers that only it needs move here. The worker receives its dependencies as arguments — no module-level globals, fully testable.

```python
def make_play_script(analysis: TrackAnalysis, track_id: str) -> MixScript: ...

def load_one_track(
    analysis: TrackAnalysis, track_id: str, ref_bpm: float
) -> tuple[dict, dict]: ...

def merge_transition(
    global_script: MixScript,
    sub_script: MixScript,
    current_id: str,
    next_id: str,
    offset: int,
) -> tuple[MixScript, int]: ...

def pick_next_track(
    current: TrackAnalysis,
    pool: list[str],
    library: Library,
    model: str,
) -> str: ...

async def dj_worker(
    dj_id: str,
    dj_store: DjSessionStore,
    audio_store: AudioSessionStore,
    library: Library,
) -> None:
    # Exact same logic as current _dj_worker.
    # Reads/writes DjSessionState fields instead of dict keys.
```

`server.py` route becomes:

```python
@app.post("/api/dj/start")
async def dj_start(
    req: DjStartRequest,
    background_tasks: BackgroundTasks,
    lib: Library = Depends(get_library),
):
    pool  = [h for v in req.pool  if (h := lib.resolve(v))]
    queue = [h for v in req.queue if (h := lib.resolve(v))]
    if not pool and not queue:
        pool = [e.hash for e in lib.get_all()]
    dj_id = str(uuid.uuid4())
    state = DjSessionState(
        dj_id=dj_id, status="starting", model=req.model,
        let_claude_pick=req.let_claude_pick, pool=pool, queue=queue,
    )
    _dj_store.create(dj_id, state)
    background_tasks.add_task(dj_worker, dj_id, _dj_store, _audio_store, lib)
    return {"dj_id": dj_id}
```

---

## DSP Improvements (`executor.py`)

Seven targeted fixes. All independent — each can be tested in isolation.

### 1. Equal-power crossfades

Replaces linear gain ramp in `_apply_gain_ramp`. Linear causes a ~3 dB amplitude dip at the crossover midpoint. Equal-power maintains constant perceived loudness throughout.

```python
# fade in: sin curve   fade out: cos curve
# sin²(x) + cos²(x) = 1 → tracks always sum to unity power
if gain_at_ramp_end > gain_at_ramp_start:   # fade in
    gain = np.sin(frac * np.pi / 2)
else:                                        # fade out
    gain = np.cos(frac * np.pi / 2)
```

### 2. Smooth bass swap (ramp over 2 bars)

Replaces instant `high_pass_filter(layer[swap_ms:], 200)` hard cut. Crossfades from the original signal to the HPF-filtered signal over `bars_to_ms(2, ref_bpm)` ms.

```python
ramp_ms = bars_to_ms(2, ref_bpm)
original_tail = layer[swap_ms : swap_ms + ramp_ms]
filtered_tail = high_pass_filter(original_tail, 200)
blended = original_tail.overlay(
    _apply_gain_ramp(filtered_tail, swap_ms, swap_ms, swap_ms + ramp_ms, 0.0, 1.0)
)
blended = _apply_gain_ramp(blended, swap_ms, swap_ms, swap_ms + ramp_ms, 1.0, 0.0).overlay(
    _apply_gain_ramp(filtered_tail, swap_ms, swap_ms, swap_ms + ramp_ms, 0.0, 1.0)
)
layer = layer[:swap_ms] + blended + high_pass_filter(layer[swap_ms + ramp_ms:], 200)
```

### 3. Loop boundary crossfade (16 ms overlap-add)

Removes click at the splice point where each loop repeat begins. Crossfades the tail of one repeat into the head of the next.

```python
LOOP_XFADE_MS = 16
tail = phrase[-LOOP_XFADE_MS:]
head = phrase[:LOOP_XFADE_MS]
seam = tail.fade_out(LOOP_XFADE_MS).overlay(head.fade_in(LOOP_XFADE_MS))
# use seam as the boundary region between repeats
```

### 4. Soft limiter on render output

Prevents clipping when two tracks overlap during crossfade. Applied to the final canvas after all track layers are mixed.

```python
samples = np.array(canvas.get_array_of_samples(), dtype=np.float32)
max_val = float(1 << (canvas.sample_width * 8 - 1))
normalized = samples / max_val
# tanh soft clip at -1 dBFS ceiling (0.891 ≈ 10^(-1/20))
limited = np.tanh(normalized * 0.891) * 0.891
out = np.clip(limited * max_val, -max_val, max_val - 1).astype(np.int16)
canvas = canvas._spawn(out.tobytes())
```

Applied in both `render_chunk()` (streaming) and `render()` (offline).

### 5. Loudness matching

Uses `loudness_dbfs` already stored in `LibraryEntry`. Applies a gain trim before time-stretching so all tracks hit `-14.0 dBFS`. Prevents jarring level jumps between tracks.

```python
TARGET_DBFS = -14.0

def apply_loudness_match(seg: AudioSegment, source_dbfs: float) -> AudioSegment:
    gain_db = TARGET_DBFS - source_dbfs
    if abs(gain_db) > 0.5:
        return seg.apply_gain(gain_db)
    return seg
```

Called in `load_one_track()` after loading, before time-stretching. (`_load_session_audio` is deleted — the auto-DJ path only uses `load_one_track`.)

### 6. Offline/streaming render parity

`render()` currently uses pydub's `seg.fade_in(ms)` / `seg.fade_out(ms)` (linear curve). `render_chunk()` uses `_apply_gain_ramp`. They produce different-sounding output for the same script.

Fix: replace pydub fade calls in `render()` with `_apply_gain_ramp` using equal-power curves, matching the streaming path exactly.

### 7. EQ shelving filters

Replaces brick-wall `high_pass_filter` / `low_pass_filter` in `apply_eq` with first-order shelving filters via `scipy.signal` (already available as a librosa dependency).

```python
from scipy.signal import sosfilt, butter

def _shelf_filter(samples: np.ndarray, sr: int, cutoff: int, gain_db: float, shelf: str) -> np.ndarray:
    # shelf: 'low' or 'high'
    # gain_db: negative = cut, positive = boost
    sos = butter(1, cutoff / (sr / 2), btype=shelf, output='sos')
    gain = 10 ** (gain_db / 20)
    filtered = sosfilt(sos, samples)
    return samples + (filtered - samples) * abs(gain_db) / 12.0  # partial blend

def apply_eq(audio: AudioSegment, low: float, mid: float, high: float) -> AudioSegment:
    # low/high: 0.0 = full cut, 1.0 = unity. mid: 0.0–1.0 maps to −6…+6 dB
    # Uses shelving instead of brick-wall cuts
    ...
```

---

## Deleted Endpoints

The following endpoints are removed. They belonged to the old analyze-then-plan CLI workflow; the frontend does not use them.

- `POST /api/analyze`
- `GET  /api/analyze/{job_id}`
- `POST /api/plan`

The associated `_analyze_jobs` dict and `_run_analyze` / `_load_session_audio` / `_load_audio_for_script` functions in `server.py` are also deleted. The auto-DJ path (`dj_worker`) does its own audio loading via `load_one_track()` in `dj_session.py`.

---

## Tests

No real audio files required. Synthetic `AudioSegment.silent()` stubs and small numpy arrays cover all assertions.

### `tests/test_normalizer.py`
- Duration clamped to `[4, 64]` bars
- Phrase snapping: 13 bars → 16, 5 bars → 8
- `bass_swap` auto-injected when missing from a transition window
- `incoming_track` backfilled on existing `bass_swap` with no `incoming_track`
- Orphaned `fade_in` gets injected `play` at `start_bar + duration_bars`
- 3-track set: two transitions, two `bass_swap` injections, correct `incoming_track` on each

### `tests/test_executor.py`
- Equal-power: `sin²(frac) + cos²(frac) == 1.0` within 1% at 100 sample points
- `compute_cursors_at_ms` returns `active=True` at correct bar for `play`, `fade_in`
- `compute_cursors_at_ms` returns `bass_cut=True` after `bass_swap` fires
- `render_chunk` on 2-track minimal script returns non-silent `AudioSegment`
- Limiter: output samples stay in `[-1.0, 1.0]` when input is driven 6 dB hot

### `tests/test_library.py`
- `Library.load()` on missing file starts empty, no exception
- `upsert` + `save` + fresh `Library.load()` round-trips all fields
- `resolve(hash)` returns hash when present
- `resolve(path)` finds by path match
- `resolve("nonexistent")` returns `None`
- Atomic save: truncated `.tmp` file leaves original intact

### `tests/test_dsp.py`
- Soft limiter output range: all samples in `[-1.0, 1.0]` for 6 dB overdrive input
- Loudness match: after trim, RMS of result within 0.5 dB of target
- Smooth bass swap: no single-sample discontinuity > 3× local RMS at swap boundary

---

## Interaction Flows (unchanged)

The public API contract is identical. No endpoint signatures change. The frontend requires zero modifications.

```
POST /api/dj/start       → {dj_id}
GET  /api/dj/{dj_id}     → DjState (deck_a, deck_b, session_id, ref_bpm, queue, history)
POST /api/dj/{dj_id}/queue
GET  /api/session/{id}   → loading state
GET  /api/status/{id}    → current_bar, buffer_depth_bars
GET  /api/script/{id}    → MixScript JSON
GET  /api/library        → tracks
POST /api/library/scan   → {scan_id}
GET  /api/library/scan/{scan_id}
WS   /ws/stream/{id}     → float32 PCM
```

---

## What's Explicitly Out of Scope

- Changes to `mix_director.py` — Claude's planning prompt is separate work
- Changes to `analyze.py` — analysis pipeline is working well
- `audio_queue.py` refactor — `ChunkScheduler` is well-isolated already
- New API endpoints
- Multi-user / multi-session support
- Persistent session storage (sessions remain in-process)
