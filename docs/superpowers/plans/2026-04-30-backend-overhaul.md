# Claude DJ Backend Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 1024-line `server.py` monolith into focused modules with typed state, fix audio quality with 7 DSP improvements, and delete dead legacy endpoints.

**Architecture:** `server.py` becomes routes-only (~200 lines); business logic moves to `library.py`, `dj_session.py`, and `state.py`. Five global plain-dict stores replaced by typed dataclasses managed through thin store wrappers. Seven targeted fixes in `executor.py` (equal-power crossfades, smooth bass swap, loop boundary crossfade, soft limiter, loudness matching, render parity, EQ shelving). Tests in `claude-dj/tests/` use synthetic `AudioSegment.silent()` and numpy arrays — no real audio files needed.

**Tech Stack:** Python 3.12, FastAPI, pydub, numpy, scipy (already installed as a librosa dependency), pytest. No new dependencies.

---

### Task 1: state.py — Typed dataclasses and store wrappers

**Files:**
- Create: `claude-dj/state.py`

- [ ] **Step 1: Create state.py**

```python
# claude-dj/state.py
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Literal, Optional


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
    loudness_dbfs: float = -14.0


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


class ScanJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}

    def create(self, scan_id: str) -> ScanJob:
        job = ScanJob(scan_id=scan_id, status="running")
        self._jobs[scan_id] = job
        return job

    def get(self, scan_id: str) -> Optional[ScanJob]:
        return self._jobs.get(scan_id)


class AudioSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AudioSession] = {}

    def create(self, session_id: str, sess: AudioSession) -> None:
        self._sessions[session_id] = sess

    def get(self, session_id: str) -> Optional[AudioSession]:
        return self._sessions.get(session_id)

    def values(self):
        return self._sessions.values()


class DjSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, DjSessionState] = {}

    def create(self, dj_id: str, state: DjSessionState) -> None:
        self._sessions[dj_id] = state

    def get(self, dj_id: str) -> Optional[DjSessionState]:
        return self._sessions.get(dj_id)
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from state import LibraryEntry, ScanJob, DjDeckA, DjDeckB, DjSessionState, AudioSession, ScanJobStore, AudioSessionStore, DjSessionStore; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/state.py && git commit -m "feat(backend): add typed state dataclasses and store wrappers"
```

---

### Task 2: library.py + tests — Library class (TDD)

**Files:**
- Create: `claude-dj/tests/conftest.py`
- Create: `claude-dj/tests/test_library.py`
- Create: `claude-dj/library.py`

- [ ] **Step 1: Create tests directory and conftest.py**

```bash
mkdir -p /Users/DantesFolder/Claude\ DJ/claude-dj/tests
```

```python
# claude-dj/tests/conftest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 2: Write failing tests for Library**

```python
# claude-dj/tests/test_library.py
from datetime import datetime
from pathlib import Path

import pytest

from state import LibraryEntry
from library import Library


def _entry(hash="abc123", path="/music/t.mp3", title="Test", artist="Artist") -> LibraryEntry:
    return LibraryEntry(
        hash=hash, path=path, title=title, artist=artist,
        bpm=128.0, key_camelot="8B", key_standard="C major",
        energy=7, duration_s=300.0, energy_curve="56789",
        cue_points=[{"name": "drop", "bar": 32, "type": "phrase_start"}],
        first_downbeat_s=0.5, analyzed_at=datetime.utcnow().isoformat(),
        loudness_dbfs=-14.0,
    )


def test_load_on_missing_file_starts_empty(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    assert lib.get_all() == []


def test_upsert_then_get_returns_entry(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    e = _entry()
    lib.upsert("abc123", e)
    assert lib.get("abc123") == e


def test_save_and_reload_preserves_all_fields(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())

    lib2 = Library(tmp_path)
    lib2.load()
    loaded = lib2.get("abc123")
    assert loaded is not None
    assert loaded.title == "Test"
    assert loaded.bpm == 128.0
    assert loaded.cue_points == [{"name": "drop", "bar": 32, "type": "phrase_start"}]
    assert loaded.loudness_dbfs == -14.0


def test_resolve_by_hash(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    assert lib.resolve("abc123") == "abc123"


def test_resolve_by_path(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry(path="/music/t.mp3"))
    assert lib.resolve("/music/t.mp3") == "abc123"


def test_resolve_nonexistent_returns_none(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    assert lib.resolve("nonexistent") is None


def test_atomic_save_leaves_no_tmp_file(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    assert not (tmp_path / "library.json.tmp").exists()
    assert (tmp_path / "library.json").exists()


def test_get_all_sorted_by_artist_then_title(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("h1", _entry("h1", title="Zeal", artist="Beta"))
    lib.upsert("h2", _entry("h2", title="Alpha", artist="Alpha"))
    lib.upsert("h3", _entry("h3", title="Bravo", artist="Alpha"))
    result = lib.get_all()
    assert [e.hash for e in result] == ["h2", "h3", "h1"]


def test_to_analysis_builds_track_analysis(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    analysis = lib.to_analysis("abc123", "T1")
    assert analysis.id == "T1"
    assert analysis.title == "Test"
    assert analysis.bpm == 128.0
    assert analysis.key.camelot == "8B"
    assert analysis.loudness_dbfs == -14.0
```

- [ ] **Step 3: Run tests — verify they all fail with ImportError**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_library.py -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'library'`

- [ ] **Step 4: Create library.py**

```python
# claude-dj/library.py
from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from schema import BarGrid, CuePoint, KeyInfo, StemPaths, TrackAnalysis
from state import LibraryEntry


class Library:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._file = self._cache_dir / "library.json"
        self._entries: dict[str, LibraryEntry] = {}

    def load(self) -> None:
        if not self._file.exists():
            self._entries = {}
            return
        try:
            raw: dict[str, dict] = json.loads(self._file.read_text())
            self._entries = {}
            for h, v in raw.items():
                # Tolerate missing loudness_dbfs from older library.json files
                v.setdefault("loudness_dbfs", -14.0)
                self._entries[h] = LibraryEntry(**v)
        except Exception:
            self._entries = {}

    def save(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".json.tmp")
        data = {h: dataclasses.asdict(e) for h, e in self._entries.items()}
        tmp.write_text(json.dumps(data, indent=2))
        os.rename(str(tmp), str(self._file))

    def get(self, hash: str) -> Optional[LibraryEntry]:
        return self._entries.get(hash)

    def get_all(self) -> list[LibraryEntry]:
        return sorted(
            self._entries.values(),
            key=lambda e: (e.artist.lower(), e.title.lower()),
        )

    def upsert(self, hash: str, entry: LibraryEntry) -> None:
        self._entries[hash] = entry
        self.save()

    def resolve(self, val: str) -> Optional[str]:
        if val in self._entries:
            return val
        for h, e in self._entries.items():
            if e.path == val:
                return h
        return None

    def to_analysis(self, hash: str, track_id: str) -> TrackAnalysis:
        e = self._entries[hash]
        key_std = e.key_standard
        tonic = key_std.split()[0]
        mode = "minor" if key_std.endswith("m") or "minor" in key_std else "major"
        bpm = float(e.bpm)
        dur = float(e.duration_s)
        n_bars = max(1, int(dur * bpm / 240))
        return TrackAnalysis(
            id=track_id,
            title=e.title,
            artist=e.artist,
            file=e.path,
            duration_s=dur,
            bpm=bpm,
            first_downbeat_s=float(e.first_downbeat_s),
            key=KeyInfo(
                camelot=e.key_camelot,
                standard=key_std,
                mode=mode,
                tonic=tonic,
            ),
            energy_overall=int(e.energy),
            loudness_dbfs=float(e.loudness_dbfs),
            bar_grid=BarGrid(n_bars=n_bars, beats_per_bar=4),
            energy_curve_per_bar=e.energy_curve,
            sections=[],
            cue_points=[
                CuePoint(name=c["name"], bar=c["bar"], type=c.get("type", "phrase_start"))
                for c in e.cue_points
            ],
            stems=StemPaths(vocals="", drums="", bass="", other=""),
        )
```

- [ ] **Step 5: Run tests — verify they all pass**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_library.py -v
```

Expected: `9 passed`

- [ ] **Step 6: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/library.py claude-dj/tests/conftest.py claude-dj/tests/test_library.py && git commit -m "feat(backend): add Library class with atomic save and typed entries"
```

---

### Task 3: dj_session.py — Extract DJ worker and helpers

**Files:**
- Modify: `claude-dj/executor.py` (add `apply_loudness_match` — required by dj_session.py)
- Create: `claude-dj/dj_session.py`

- [ ] **Step 1: Add `apply_loudness_match` and `TARGET_DBFS` to executor.py**

Add these lines after the `apply_eq` function (around line 88):

```python
TARGET_DBFS = -14.0


def apply_loudness_match(seg: "AudioSegment", source_dbfs: float) -> "AudioSegment":
    gain_db = TARGET_DBFS - source_dbfs
    if abs(gain_db) > 0.5:
        return seg.apply_gain(gain_db)
    return seg
```

- [ ] **Step 2: Verify executor imports cleanly**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from executor import apply_loudness_match, TARGET_DBFS; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Create dj_session.py**

```python
# claude-dj/dj_session.py
"""
Auto-DJ session worker and helpers.
Extracted from server.py so that routes stay thin and this module is testable.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import time as _time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from pydub import AudioSegment

from audio_queue import ChunkScheduler
from executor import (
    _stem_dir_for_track, apply_loudness_match, bars_to_ms,
    load_track, time_stretch,
)
from library import Library
from mix_director import direct_mix, select_next_track
from normalizer import normalize
from schema import MixAction, MixScript, MixTrackRef, TrackAnalysis
from state import (
    AudioSession, AudioSessionStore, DjDeckA, DjDeckB,
    DjSessionState, DjSessionStore,
)

_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dj-worker")


def make_play_script(analysis: TrackAnalysis, track_id: str) -> MixScript:
    return MixScript(
        mix_title="Claude DJ — Live",
        reasoning=f"Now playing: {analysis.title}",
        tracks=[MixTrackRef(
            id=track_id, path=analysis.file,
            bpm=analysis.bpm, first_downbeat_s=analysis.first_downbeat_s,
        )],
        actions=[MixAction(type="play", track=track_id, at_bar=0, from_bar=0)],
    )


def load_one_track(
    analysis: TrackAnalysis,
    track_id: str,
    ref_bpm: float,
) -> tuple[dict, dict]:
    """Load, loudness-match, and time-stretch one track. Returns (loaded_dict, stem_layers_dict)."""
    seg = load_track(analysis.file)
    first_db_ms = int(analysis.first_downbeat_s * 1000)
    if first_db_ms > 0:
        seg = seg[first_db_ms:]
    seg = apply_loudness_match(seg, analysis.loudness_dbfs)
    seg = time_stretch(seg, analysis.bpm, ref_bpm)
    loaded = {track_id: seg}

    stems: dict[tuple[str, str], AudioSegment] = {}
    for stem_name in ("drums", "bass", "vocals", "other"):
        p = Path(getattr(analysis.stems, stem_name, ""))
        if p.exists():
            s = AudioSegment.from_wav(str(p))
            s = apply_loudness_match(s, analysis.loudness_dbfs)
            s = time_stretch(s, analysis.bpm, ref_bpm)
            if s.frame_rate != seg.frame_rate:
                s = s.set_frame_rate(seg.frame_rate)
            stems[(track_id, stem_name)] = s

    if loaded[track_id].frame_rate != seg.frame_rate:
        loaded[track_id] = loaded[track_id].set_frame_rate(seg.frame_rate)

    return loaded, stems


def merge_transition(
    global_script: MixScript,
    sub_script: MixScript,
    current_id: str,
    next_id: str,
    offset: int,
) -> tuple[MixScript, int]:
    """
    Merge a 2-track sub-script (T1=current_id, T2=next_id) into global_script,
    offsetting all bar numbers by `offset`. Returns (new_global_script, next_start_bar).
    """
    sub_id_map = {"T1": current_id, "T2": next_id}

    new_tracks = list(global_script.tracks)
    next_ref = next((t for t in sub_script.tracks if t.id == "T2"), None)
    if next_ref and not any(t.id == next_id for t in new_tracks):
        new_tracks.append(dataclasses.replace(next_ref, id=next_id))

    new_actions = list(global_script.actions)
    next_start_bar = offset

    for a in sub_script.actions:
        if a.type == "play" and a.track == "T1" and (a.at_bar or 0) == 0:
            continue
        global_track = sub_id_map.get(a.track, a.track)
        new_a = dataclasses.replace(
            a,
            track     = global_track,
            at_bar    = ((a.at_bar    or 0) + offset) if a.at_bar    is not None else None,
            start_bar = ((a.start_bar or 0) + offset) if a.start_bar is not None else None,
            bar       = ((a.bar       or 0) + offset) if a.bar       is not None else None,
        )
        new_actions.append(new_a)
        if a.type == "play" and a.track == "T2":
            next_start_bar = (a.at_bar or 0) + offset

    def _action_bar(act: MixAction) -> int:
        return act.at_bar or act.start_bar or act.bar or 0

    return (
        MixScript(
            mix_title=global_script.mix_title,
            reasoning=global_script.reasoning,
            tracks=new_tracks,
            actions=sorted(new_actions, key=_action_bar),
        ),
        next_start_bar,
    )


def pick_next_track(
    current: TrackAnalysis,
    pool: list[str],
    library: Library,
    model: str,
) -> str:
    """Ask Claude to pick the best-fitting next track from the pool."""
    candidates = [
        library.to_analysis(h, h)
        for h in pool[:10]
        if library.get(h) is not None
    ]
    if not candidates:
        return pool[0]
    chosen_id = select_next_track(current, candidates, model)
    if chosen_id in pool:
        return chosen_id
    return pool[0]


async def dj_worker(
    dj_id: str,
    dj_store: DjSessionStore,
    audio_store: AudioSessionStore,
    library: Library,
) -> None:
    """Rolling auto-DJ pipeline: T1 → T2 → T3 … with lazy planning."""
    state = dj_store.get(dj_id)
    model = state.model
    loop = asyncio.get_running_loop()

    def _pop_next() -> Optional[str]:
        return state.queue.pop(0) if state.queue else None

    def _available_pool() -> list[str]:
        return [h for h in state.pool if h not in state.history]

    # ── Phase 1: start T1 ───────────────────────────────────────────────────
    first_hash = _pop_next() or (_available_pool() or [None])[0]
    if not first_hash or library.get(first_hash) is None:
        state.status = "error"
        state.error = "No tracks available to start"
        return

    state.history.append(first_hash)
    state.deck_b = DjDeckB(status="analyzing", title="first track")

    try:
        from analyze import analyze_track as _analyze_track
        first_entry = library.get(first_hash)
        state.deck_b = DjDeckB(status="analyzing", title=first_entry.title)
        first_analysis = await loop.run_in_executor(
            _bg_executor, _analyze_track,
            first_entry.path, "T1", True,
        )
    except Exception as exc:
        state.status = "error"
        state.error = f"T1 analysis failed: {exc}"
        return

    ref_bpm = first_analysis.bpm
    try:
        state.deck_b = DjDeckB(status="loading", title=first_analysis.title)
        loaded, stems = await loop.run_in_executor(
            _bg_executor, load_one_track, first_analysis, "T1", ref_bpm,
        )
    except Exception as exc:
        state.status = "error"
        state.error = f"T1 load failed: {exc}"
        return

    script = make_play_script(first_analysis, "T1")
    scheduler = ChunkScheduler(script, loaded, stems, ref_bpm)
    scheduler.total_mix_ms = len(loaded["T1"]) * 4
    await scheduler.start()

    session_id = str(uuid.uuid4())
    audio_store.create(session_id, AudioSession(
        session_id    = session_id,
        status        = "ready",
        script        = script,
        scheduler     = scheduler,
        ref_bpm       = ref_bpm,
        tracks        = [dataclasses.asdict(t) for t in script.tracks],
        load_progress = 1,
        load_total    = 1,
    ))

    state.session_id        = session_id
    state.status            = "playing"
    state.ref_bpm           = ref_bpm
    state.track_counter     = 1
    state.current_start_bar = 0
    state.deck_a = DjDeckA(
        track_id  = "T1",
        hash      = first_hash,
        title     = first_analysis.title,
        start_bar = 0,
    )
    state.deck_b = None
    current_analysis = first_analysis

    # ── Phase 2: rolling transitions ────────────────────────────────────────
    for _step in range(1, 200):
        if state.status != "playing":
            break

        current_id    = f"T{state.track_counter}"
        current_hash  = state.deck_a.hash
        current_start = state.current_start_bar

        next_hash = _pop_next()
        if not next_hash:
            pool = _available_pool()
            if not pool:
                break
            if state.let_claude_pick and os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    next_hash = await loop.run_in_executor(
                        _bg_executor, pick_next_track,
                        current_analysis, pool, library, model,
                    )
                except Exception:
                    next_hash = pool[0]
            else:
                next_hash = pool[0]

        if not next_hash or library.get(next_hash) is None:
            break

        state.history.append(next_hash)
        next_tc = state.track_counter + 1
        next_id = f"T{next_tc}"
        next_entry = library.get(next_hash)
        state.deck_b = DjDeckB(status="analyzing", title=next_entry.title)

        try:
            from analyze import analyze_track as _analyze_track
            next_analysis = await loop.run_in_executor(
                _bg_executor, _analyze_track,
                next_entry.path, next_id, True,
            )
        except Exception as exc:
            print(f"[dj_worker] analyze {next_id} failed: {exc}")
            state.deck_b = None
            continue

        state.deck_b = DjDeckB(status="planning", title=next_analysis.title)

        try:
            sub_script: MixScript = await loop.run_in_executor(
                _bg_executor, direct_mix,
                [current_analysis, next_analysis], model, None,
            )
            sub_script = normalize(sub_script)
        except Exception as exc:
            print(f"[dj_worker] plan {current_id}→{next_id} failed: {exc}")
            state.deck_b = None
            continue

        state.deck_b = DjDeckB(status="loading", title=next_analysis.title)

        try:
            extra_loaded, extra_stems = await loop.run_in_executor(
                _bg_executor, load_one_track, next_analysis, next_id, ref_bpm,
            )
        except Exception as exc:
            print(f"[dj_worker] load {next_id} failed: {exc}")
            state.deck_b = None
            continue

        audio_sess = audio_store.get(session_id)
        global_script = audio_sess.script
        new_script, next_start_bar = merge_transition(
            global_script, sub_script, current_id, next_id, current_start,
        )
        scheduler.extend(new_script, extra_loaded, extra_stems)
        audio_sess.script = new_script

        state.deck_b = DjDeckB(status="ready", title=next_analysis.title)
        state.track_counter = next_tc

        bars_remaining = max(0, next_start_bar - scheduler.current_bar)
        secs_remaining = bars_remaining * (4 * 60 / ref_bpm)
        deadline = _time.monotonic() + secs_remaining + 4.0
        while _time.monotonic() < deadline:
            await asyncio.sleep(2.0)
            if state.status != "playing":
                return

        state.deck_a = DjDeckA(
            track_id  = next_id,
            hash      = next_hash,
            title     = next_analysis.title,
            start_bar = next_start_bar,
        )
        state.deck_b = None
        state.current_start_bar = next_start_bar
        current_analysis = next_analysis
```

- [ ] **Step 4: Verify dj_session imports cleanly**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from dj_session import make_play_script, load_one_track, merge_transition, pick_next_track, dj_worker; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/dj_session.py claude-dj/executor.py && git commit -m "feat(backend): add dj_session module and apply_loudness_match"
```

---

### Task 4: executor.py — Equal-power crossfades

**Files:**
- Modify: `claude-dj/executor.py` (replace linear ramp with sin/cos in `_apply_gain_ramp`)
- Modify: `claude-dj/tests/test_executor.py` (create file with failing test)

- [ ] **Step 1: Write failing test**

Create `claude-dj/tests/test_executor.py` with this content:

```python
# claude-dj/tests/test_executor.py
import numpy as np
import pytest
from pydub import AudioSegment

from executor import _apply_gain_ramp, bars_to_ms, compute_cursors_at_ms, render_chunk
from schema import MixAction, MixScript, MixTrackRef


def _noise(ms=1000, rate=44100) -> AudioSegment:
    """Non-silent mono audio for testing gain ramps."""
    rng = np.random.default_rng(42)
    samples = (rng.integers(-10000, 10000, int(rate * ms / 1000), dtype=np.int16))
    return AudioSegment(samples.tobytes(), frame_rate=rate, sample_width=2, channels=1)


def _script(actions, n_tracks=1) -> MixScript:
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=128.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


def test_equal_power_sum_to_unity():
    """sin²(frac) + cos²(frac) == 1 — fade_in² + fade_out² == source² at every sample."""
    audio = _noise(1000)
    ramp_ms = 1000
    fade_in  = _apply_gain_ramp(audio, 0, 0, ramp_ms, 0.0, 1.0)
    fade_out = _apply_gain_ramp(audio, 0, 0, ramp_ms, 1.0, 0.0)

    max_val = float(1 << (audio.sample_width * 8 - 1))
    src_n  = np.array(audio.get_array_of_samples(),    dtype=np.float32) / max_val
    in_n   = np.array(fade_in.get_array_of_samples(),  dtype=np.float32) / max_val
    out_n  = np.array(fade_out.get_array_of_samples(), dtype=np.float32) / max_val

    src_pow = src_n ** 2
    sum_pow = in_n  ** 2 + out_n ** 2
    nonzero = src_pow > 1e-6
    ratio = sum_pow[nonzero] / src_pow[nonzero]
    assert np.allclose(ratio, 1.0, atol=0.01), f"max deviation: {np.max(np.abs(ratio - 1.0)):.4f}"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_executor.py::test_equal_power_sum_to_unity -v
```

Expected: `FAILED` (linear ramp gives `frac² + (1-frac)²` which dips below 1 at mid-point)

- [ ] **Step 3: Replace linear ramp in `_apply_gain_ramp` with sin/cos**

In `claude-dj/executor.py`, find the `_apply_gain_ramp` function (lines 100–130). Replace the `gain =` assignment inside the `else` branch:

**Old** (line 125):
```python
        gain = (gain_at_ramp_start + (gain_at_ramp_end - gain_at_ramp_start) * frac).astype(np.float32)
```

**New**:
```python
        if gain_at_ramp_end > gain_at_ramp_start:   # fade in: sin curve
            gain = np.sin(frac * np.pi / 2).astype(np.float32)
        else:                                        # fade out: cos curve
            gain = np.cos(frac * np.pi / 2).astype(np.float32)
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_executor.py::test_equal_power_sum_to_unity -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py claude-dj/tests/test_executor.py && git commit -m "feat(dsp): equal-power crossfades using sin/cos gain curves"
```

---

### Task 5: executor.py — Render parity

**Files:**
- Modify: `claude-dj/executor.py` (replace pydub `fade_in`/`fade_out` calls in `render()` with `_apply_gain_ramp`)

The offline `render()` currently uses pydub's linear `.fade_in()` / `.fade_out()` methods while `render_chunk()` uses `_apply_gain_ramp`. After Task 4 both should use the equal-power curves. This task fixes the `render()` path.

- [ ] **Step 1: Fix fade_in action handler in render()**

In `claude-dj/executor.py`, find the `fade_in` action handler in `render()` (around line 478–483):

**Old**:
```python
            else:
                src = loaded[tid]
                clip = src[from_ms:from_ms + fade_ms].fade_in(fade_ms)
                layers[tid] = layers[tid].overlay(clip, position=at_ms)
```

**New**:
```python
            else:
                src  = loaded[tid]
                clip = src[from_ms:from_ms + fade_ms]
                clip = _apply_gain_ramp(clip, 0, 0, fade_ms, 0.0, 1.0)
                layers[tid] = layers[tid].overlay(clip, position=at_ms)
```

- [ ] **Step 2: Fix the stem fade_in path as well**

In the same `fade_in` handler, find (around line 476–479):

**Old**:
```python
                if mixed is not None:
                    layers[tid] = layers[tid].overlay(mixed.fade_in(fade_ms), position=at_ms)
```

**New**:
```python
                if mixed is not None:
                    mixed = _apply_gain_ramp(mixed, 0, 0, fade_ms, 0.0, 1.0)
                    layers[tid] = layers[tid].overlay(mixed, position=at_ms)
```

- [ ] **Step 3: Fix fade_out action handler in render()**

Find the `fade_out` action handler (around line 485–495):

**Old**:
```python
        elif action.type == "fade_out":
            fade_ms  = bars_to_ms(action.duration_bars or 8, ref_bpm)
            start_ms = bars_to_ms(action.start_bar or 0, ref_bpm)
            layer    = layers[tid]
            faded    = layer[start_ms:start_ms + fade_ms].fade_out(fade_ms)
            silence_ms = max(0, len(layer) - start_ms - fade_ms)
            layers[tid] = (
                layer[:start_ms]
                + faded
                + AudioSegment.silent(duration=silence_ms, frame_rate=target_rate)
            )
```

**New**:
```python
        elif action.type == "fade_out":
            fade_ms    = bars_to_ms(action.duration_bars or 8, ref_bpm)
            start_ms   = bars_to_ms(action.start_bar or 0, ref_bpm)
            layer      = layers[tid]
            chunk      = layer[start_ms:start_ms + fade_ms]
            faded      = _apply_gain_ramp(chunk, 0, 0, fade_ms, 1.0, 0.0)
            silence_ms = max(0, len(layer) - start_ms - fade_ms)
            layers[tid] = (
                layer[:start_ms]
                + faded
                + AudioSegment.silent(duration=silence_ms, frame_rate=target_rate)
            )
```

- [ ] **Step 4: Verify executor still imports and render_chunk test still passes**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from executor import render, render_chunk; print('ok')" && python -m pytest tests/test_executor.py -v
```

Expected: `ok` then `1 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py && git commit -m "feat(dsp): render/render_chunk parity using _apply_gain_ramp for fades"
```

---

### Task 6: executor.py — Smooth bass swap

**Files:**
- Modify: `claude-dj/executor.py` (new `_apply_smooth_bass_swap` helper, use in `render()`)

Replaces the instant HPF hard cut with a 2-bar crossfade from original to HPF-filtered signal.

- [ ] **Step 1: Add `_apply_smooth_bass_swap` to executor.py**

Insert this function after `_apply_gain_ramp` (after line 130):

```python
def _apply_smooth_bass_swap(
    layer: AudioSegment,
    swap_ms: int,
    ref_bpm: float,
) -> AudioSegment:
    """
    Crossfade from original signal to HPF-filtered signal over 2 bars,
    then continue with full HPF after the ramp. Avoids the click from an
    instant high-pass cut.
    """
    if swap_ms >= len(layer):
        return layer
    ramp_ms  = bars_to_ms(2, ref_bpm)
    ramp_end = min(swap_ms + ramp_ms, len(layer))
    region   = layer[swap_ms:ramp_end]
    actual_ms = len(region)

    original_fade = _apply_gain_ramp(region, 0, 0, actual_ms, 1.0, 0.0)
    filtered_fade = _apply_gain_ramp(high_pass_filter(region, 200), 0, 0, actual_ms, 0.0, 1.0)
    blended = original_fade.overlay(filtered_fade)

    result = layer[:swap_ms] + blended
    if ramp_end < len(layer):
        result = result + high_pass_filter(layer[ramp_end:], 200)
    return result
```

- [ ] **Step 2: Use `_apply_smooth_bass_swap` in the `bass_swap` handler in `render()`**

Find the `bass_swap` handler in `render()` (around line 497–504). Replace just the outgoing-track HPF block:

**Old**:
```python
            layer = layers[tid]
            if swap_ms < len(layer):
                tail = high_pass_filter(layer[swap_ms:], 200)
                layers[tid] = layer[:swap_ms] + tail
```

**New**:
```python
            layers[tid] = _apply_smooth_bass_swap(layers[tid], swap_ms, ref_bpm)
```

- [ ] **Step 3: Verify executor imports cleanly**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from executor import _apply_smooth_bass_swap; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py && git commit -m "feat(dsp): smooth bass swap — 2-bar crossfade into HPF replaces hard cut"
```

---

### Task 7: executor.py — Loop boundary crossfade

**Files:**
- Modify: `claude-dj/executor.py` (16 ms overlap-add at loop splice in `render_chunk()`)

Eliminates the click at the point where each loop repeat restarts.

- [ ] **Step 1: Add the loop crossfade in `render_chunk()`**

In `claude-dj/executor.py`, find the loop-mode source slice in `render_chunk()` (around lines 264–295). Add the crossfade setup immediately after the phrase is sliced (after `phrase = src[...]`):

**Old** (around line 266–269):
```python
            phrase_ms = cursor.loop_phrase_ms
            phrase    = src[cursor.loop_source_offset : cursor.loop_source_offset + phrase_ms]
            if len(phrase) == 0:
                continue
            track_chunk = AudioSegment.silent(duration=chunk_ms, frame_rate=target_rate)
```

**New**:
```python
            LOOP_XFADE_MS = 16
            phrase_ms = cursor.loop_phrase_ms
            phrase    = src[cursor.loop_source_offset : cursor.loop_source_offset + phrase_ms]
            if len(phrase) == 0:
                continue

            # Crossfade the loop boundary to remove the splice click
            if len(phrase) > LOOP_XFADE_MS * 2:
                tail = phrase[-LOOP_XFADE_MS:]
                head = phrase[:LOOP_XFADE_MS]
                seam = tail.fade_out(LOOP_XFADE_MS).overlay(head.fade_in(LOOP_XFADE_MS))
                phrase = phrase[:-LOOP_XFADE_MS] + seam

            track_chunk = AudioSegment.silent(duration=chunk_ms, frame_rate=target_rate)
```

- [ ] **Step 2: Verify executor still imports**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from executor import render_chunk; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py && git commit -m "feat(dsp): 16ms overlap-add crossfade at loop boundary to remove splice click"
```

---

### Task 8: executor.py — Soft limiter

**Files:**
- Modify: `claude-dj/executor.py` (new `_apply_soft_limiter`, applied at end of `render_chunk()` and `render()`)
- Modify: `claude-dj/tests/test_executor.py` (add render_chunk non-silent test)

- [ ] **Step 1: Add `_apply_soft_limiter` to executor.py**

Add this function after `_apply_smooth_bass_swap`:

```python
def _apply_soft_limiter(canvas: AudioSegment) -> AudioSegment:
    """
    Tanh-based soft clipper at -1 dBFS ceiling. Prevents clipping when two
    tracks overlap at full gain during a crossfade.
    """
    samples = np.array(canvas.get_array_of_samples(), dtype=np.float32)
    max_val = float(1 << (canvas.sample_width * 8 - 1))
    normalized = samples / max_val
    ceiling = 0.891  # -1 dBFS ≈ 10^(-1/20)
    limited = np.tanh(normalized * ceiling) * ceiling
    out = np.clip(limited * max_val, -max_val, max_val - 1).astype(np.int16)
    return canvas._spawn(out.tobytes())
```

- [ ] **Step 2: Apply limiter at end of `render_chunk()`**

Find the `return canvas` at the end of `render_chunk()` (line 362). Replace it:

**Old**:
```python
    return canvas
```

**New**:
```python
    return _apply_soft_limiter(canvas)
```

- [ ] **Step 3: Apply limiter in `render()` before export**

Find the export block in `render()` (around line 590–597). Insert the limiter call before the export:

**Old**:
```python
    output_path = str(output_path)
    print(f"[executor] exporting to {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if export_mp3 or output_path.endswith(".mp3"):
        canvas.export(output_path, format="mp3", bitrate="320k")
    else:
        canvas.export(output_path, format="wav")
```

**New**:
```python
    canvas = _apply_soft_limiter(canvas)
    output_path = str(output_path)
    print(f"[executor] exporting to {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if export_mp3 or output_path.endswith(".mp3"):
        canvas.export(output_path, format="mp3", bitrate="320k")
    else:
        canvas.export(output_path, format="wav")
```

- [ ] **Step 4: Add render_chunk test to test_executor.py**

Append to `claude-dj/tests/test_executor.py`:

```python
def test_render_chunk_returns_non_silent_audio():
    rate = 44100
    rng  = np.random.default_rng(7)
    raw  = (rng.integers(-20000, 20000, rate * 4, dtype=np.int16))
    seg  = AudioSegment(raw.tobytes(), frame_rate=rate, sample_width=2, channels=1)

    ref_bpm  = 128.0
    chunk_ms = bars_to_ms(4, ref_bpm)
    script   = _script([MixAction(type="play", track="T1", at_bar=0, from_bar=0)])
    result   = render_chunk(script, {"T1": seg}, {}, ref_bpm, 0, chunk_ms)

    assert len(result) == chunk_ms
    samples = np.array(result.get_array_of_samples())
    assert np.any(samples != 0)
```

- [ ] **Step 5: Run all executor tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_executor.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py claude-dj/tests/test_executor.py && git commit -m "feat(dsp): tanh soft limiter on render output to prevent clipping"
```

---

### Task 9: executor.py — EQ shelving filters

**Files:**
- Modify: `claude-dj/executor.py` (replace brick-wall `apply_eq` with `_shelf_filter` + shelving)

- [ ] **Step 1: Add scipy import at top of executor.py**

After the existing imports at the top of `executor.py`, add:

```python
from scipy.signal import butter, sosfilt
```

- [ ] **Step 2: Replace `apply_eq` with shelving implementation**

Find the `apply_eq` function (lines 70–88) and replace it entirely:

**Old**:
```python
def apply_eq(audio: AudioSegment, low: float, mid: float, high: float) -> AudioSegment:
    """
    Gentle 3-band EQ approximation.
    low/high: 0.0 = full filter kill, 1.0 = bypass.
    mid: 0.0–1.0 mapped to −6…+6 dB.
    """
    low  = max(0.0, min(low,  1.0))
    mid  = max(0.0, min(mid,  1.0))
    high = max(0.0, min(high, 1.0))

    result = audio
    if low < 0.5:
        result = high_pass_filter(result, 200)
    if high < 0.5:
        result = low_pass_filter(result, 8000)
    if mid != 1.0:
        gain_db = max(-6.0, min(6.0, 12.0 * (mid - 0.5)))
        result = result + gain_db
    return result
```

**New**:
```python
def _shelf_filter(
    samples: np.ndarray, sr: int, cutoff: int, gain_db: float, shelf: str,
) -> np.ndarray:
    """
    Partial-blend shelving filter. shelf='low' | 'high'.
    gain_db negative = cut, positive = boost. Full effect at ±12 dB.
    """
    sos      = butter(1, cutoff / (sr / 2), btype=shelf, output="sos")
    filtered = sosfilt(sos, samples)
    blend    = abs(gain_db) / 12.0
    return samples + (filtered - samples) * blend


def apply_eq(audio: AudioSegment, low: float, mid: float, high: float) -> AudioSegment:
    """
    3-band EQ using shelving filters instead of brick-wall cuts.
    low/high: 0.0 = full cut, 1.0 = unity. mid: 0.0–1.0 maps to −6…+6 dB.
    """
    low  = max(0.0, min(low,  1.0))
    mid  = max(0.0, min(mid,  1.0))
    high = max(0.0, min(high, 1.0))

    sr      = audio.frame_rate
    max_val = float(1 << (audio.sample_width * 8 - 1))
    raw     = np.array(audio.get_array_of_samples(), dtype=np.float32) / max_val

    if audio.channels == 2:
        samples = raw.reshape(-1, 2)
    else:
        samples = raw.reshape(-1, 1)

    result = samples.copy()

    if low != 1.0:
        low_gain_db = 12.0 * (low - 1.0)   # 0.0 → -12 dB, 1.0 → 0 dB
        for ch in range(audio.channels):
            result[:, ch] = _shelf_filter(result[:, ch], sr, 200, low_gain_db, "high")

    if high != 1.0:
        high_gain_db = 12.0 * (high - 1.0)
        for ch in range(audio.channels):
            result[:, ch] = _shelf_filter(result[:, ch], sr, 8000, high_gain_db, "low")

    if mid != 1.0:
        gain_db = max(-6.0, min(6.0, 12.0 * (mid - 0.5)))
        result *= 10 ** (gain_db / 20)

    out = np.clip(result.flatten() * max_val, -max_val, max_val - 1).astype(np.int16)
    return audio._spawn(out.tobytes())
```

- [ ] **Step 3: Verify executor imports cleanly and tests pass**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "from executor import apply_eq, _shelf_filter; print('ok')" && python -m pytest tests/test_executor.py -v
```

Expected: `ok` then `2 passed`

- [ ] **Step 4: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/executor.py && git commit -m "feat(dsp): replace brick-wall EQ filters with scipy shelving"
```

---

### Task 10: server.py — Routes-only refactor

**Files:**
- Modify: `claude-dj/server.py` (routes only; wire up Library, typed stores, dj_worker DI; delete legacy endpoints)

This task rewrites `server.py` to ~200 lines of routes. All business logic is now in `library.py`, `dj_session.py`, and `state.py`. Delete `POST /api/analyze`, `GET /api/analyze/{job_id}`, `POST /api/plan` and their helpers.

- [ ] **Step 1: Write the new server.py**

Replace the entire contents of `claude-dj/server.py` with:

```python
"""
Claude DJ — FastAPI streaming server (routes only).

Endpoints:
  GET  /api/library              list library tracks
  POST /api/library/scan         start background folder scan
  GET  /api/library/scan/{id}    poll scan progress
  GET  /api/session/{id}         poll session loading state
  GET  /api/status/{id}          current bar + buffer depth
  GET  /api/script/{id}          mix script JSON
  WS   /ws/stream/{id}           float32 PCM chunks
  POST /api/dj/start             start auto-DJ session
  GET  /api/dj/{id}              poll DJ session state
  POST /api/dj/{id}/queue        add a track to the DJ queue
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydub import AudioSegment
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

# Load .env
_dotenv_path = Path(__file__).parent / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv_path)
    except ImportError:
        for line in _dotenv_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from analyze import CACHE_DIR, analyze_track as _analyze_track, file_hash
from audio_queue import ChunkScheduler, MIX_END_SENTINEL
from dj_session import dj_worker
from library import Library
from schema import MixScript
from state import (
    AudioSession, AudioSessionStore, DjDeckB, DjSessionState, DjSessionStore,
    LibraryEntry, ScanJobStore,
)

app = FastAPI(title="Claude DJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────

_library     = Library(CACHE_DIR)
_audio_store = AudioSessionStore()
_dj_store    = DjSessionStore()
_scan_store  = ScanJobStore()
_bg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dj-bg")
_library.load()

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}


def get_library() -> Library:
    return _library


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sanitize(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    try:
        if isinstance(obj, np.floating):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return _sanitize(obj.tolist())
    except Exception:
        pass
    return obj


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


# ── Library ───────────────────────────────────────────────────────────────────

class LibraryScanRequest(BaseModel):
    folder: str


async def _run_scan(scan_id: str, folder: str) -> None:
    from datetime import datetime
    job = _scan_store.get(scan_id)
    try:
        td = Path(folder).resolve()
        if not td.is_dir():
            job.status = "error"
            job.error  = f"Not a directory: {folder}"
            return

        files = sorted(str(p) for p in td.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        if not files:
            job.status = "error"
            job.error  = "No audio files found"
            return

        job.total = len(files)
        loop = asyncio.get_running_loop()
        known, new_count, skipped = 0, 0, 0

        for i, path in enumerate(files):
            job.progress = i
            try:
                h = await loop.run_in_executor(_bg_executor, file_hash, path)
                existing = _library.get(h)
                if existing:
                    existing.path = path
                    _library.upsert(h, existing)
                    known += 1
                    continue

                analysis = await loop.run_in_executor(
                    _bg_executor, _analyze_track, path, f"lib_{h[:8]}", True,
                )
                entry = LibraryEntry(
                    hash             = h,
                    path             = path,
                    title            = analysis.title,
                    artist           = analysis.artist,
                    bpm              = round(analysis.bpm, 1),
                    key_camelot      = analysis.key.camelot,
                    key_standard     = analysis.key.standard,
                    energy           = analysis.energy_overall,
                    duration_s       = round(analysis.duration_s, 1),
                    energy_curve     = analysis.energy_curve_per_bar,
                    cue_points       = [
                        {"name": c.name, "bar": c.bar, "type": c.type}
                        for c in analysis.cue_points
                    ],
                    first_downbeat_s = round(analysis.first_downbeat_s, 3),
                    analyzed_at      = datetime.utcnow().isoformat(),
                    loudness_dbfs    = analysis.loudness_dbfs,
                )
                _library.upsert(h, entry)
                new_count += 1
                job.new = new_count
            except Exception as exc:
                print(f"[scan] skipping {Path(path).name}: {exc}", flush=True)
                skipped += 1
                job.skipped = skipped

        job.status   = "done"
        job.progress = len(files)
        job.known    = known
        job.new      = new_count
    except Exception as exc:
        import traceback
        job.status = "error"
        job.error  = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


@app.post("/api/library/scan")
async def library_scan(req: LibraryScanRequest, background_tasks: BackgroundTasks):
    scan_id = str(uuid.uuid4())
    _scan_store.create(scan_id)
    background_tasks.add_task(_run_scan, scan_id, req.folder)
    return {"scan_id": scan_id}


@app.get("/api/library/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    job = _scan_store.get(scan_id)
    if not job:
        return JSONResponse({"error": "scan not found"}, status_code=404)
    return dataclasses.asdict(job)


@app.get("/api/library")
async def get_library_endpoint():
    tracks = [dataclasses.asdict(e) for e in _library.get_all()]
    return {"tracks": tracks, "total": len(tracks)}


# ── Session / Status / Script ─────────────────────────────────────────────────

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return {
        "status":        sess.status,
        "load_progress": sess.load_progress,
        "load_total":    sess.load_total,
        "ref_bpm":       sess.ref_bpm,
        "tracks":        sess.tracks,
        "error":         sess.error,
    }


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    sched = sess.scheduler
    if sched is None:
        return {"current_bar": 0, "buffer_depth_bars": 0,
                "ref_bpm": sess.ref_bpm, "status": sess.status}
    return {
        "current_bar":       sched.current_bar,
        "buffer_depth_bars": sched.buffer_depth_bars,
        "ref_bpm":           sess.ref_bpm,
        "tracks":            sess.tracks,
        "status":            sess.status,
    }


@app.get("/api/script/{session_id}")
async def get_script(session_id: str):
    sess = _audio_store.get(session_id)
    if not sess:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return _sanitize(dataclasses.asdict(sess.script))


# ── WebSocket stream ──────────────────────────────────────────────────────────

_SESSION_READY_TIMEOUT_S = 600


@app.websocket("/ws/stream/{session_id}")
async def stream_audio(ws: WebSocket, session_id: str):
    await ws.accept()
    sess = _audio_store.get(session_id)
    if not sess:
        await ws.close(code=4404)
        return

    waited = 0.0
    while sess.status == "loading":
        await asyncio.sleep(0.5)
        waited += 0.5
        await ws.send_text(json.dumps({
            "type": "loading",
            "progress": sess.load_progress,
            "total":    sess.load_total,
        }))
        if waited >= _SESSION_READY_TIMEOUT_S:
            await ws.send_text(json.dumps({"type": "error", "msg": "audio loading timed out"}))
            await ws.close()
            return

    if sess.status == "error":
        await ws.send_text(json.dumps({"type": "error", "msg": sess.error or "load failed"}))
        await ws.close()
        return

    sched: ChunkScheduler = sess.scheduler

    async def _handle_control() -> None:
        try:
            while True:
                text = await ws.receive_text()
                msg  = json.loads(text)
                if msg.get("action") == "seek" and "bar" in msg:
                    sched.seek(int(msg["bar"]))
        except (WebSocketDisconnect, Exception):
            pass

    control_task = asyncio.create_task(_handle_control())
    try:
        while True:
            chunk_bytes = await sched.get_chunk()
            if chunk_bytes == MIX_END_SENTINEL:
                await ws.send_text(json.dumps({"type": "end"}))
                break
            sched.advance()
            await ws.send_bytes(chunk_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[stream/{session_id}] error: {exc}")
    finally:
        control_task.cancel()


# ── Auto-DJ ───────────────────────────────────────────────────────────────────

class DjStartRequest(BaseModel):
    pool:            list[str] = []
    queue:           list[str] = []
    let_claude_pick: bool      = True
    model:           str       = "claude-sonnet-4-6"


@app.post("/api/dj/start")
async def dj_start(req: DjStartRequest, background_tasks: BackgroundTasks):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse({"error": "ANTHROPIC_API_KEY not set."}, status_code=503)

    pool  = [h for v in req.pool  if (h := _library.resolve(v))]
    queue = [h for v in req.queue if (h := _library.resolve(v))]
    if not pool and not queue:
        pool = [e.hash for e in _library.get_all()]

    dj_id = str(uuid.uuid4())
    state = DjSessionState(
        dj_id          = dj_id,
        status         = "starting",
        model          = req.model,
        let_claude_pick = req.let_claude_pick,
        pool           = pool,
        queue          = queue,
        deck_b         = DjDeckB(status="starting", title="…"),
    )
    _dj_store.create(dj_id, state)
    background_tasks.add_task(dj_worker, dj_id, _dj_store, _audio_store, _library)
    return {"dj_id": dj_id}


@app.get("/api/dj/{dj_id}")
async def get_dj_state(dj_id: str):
    state = _dj_store.get(dj_id)
    if not state:
        return JSONResponse({"error": "dj session not found"}, status_code=404)

    session_id     = state.session_id
    script_summary = None
    if session_id:
        audio_sess = _audio_store.get(session_id)
        if audio_sess and audio_sess.script:
            script_summary = _sanitize(dataclasses.asdict(audio_sess.script))

    return _sanitize({
        "status":     state.status,
        "session_id": session_id,
        "deck_a":     dataclasses.asdict(state.deck_a) if state.deck_a else None,
        "deck_b":     dataclasses.asdict(state.deck_b) if state.deck_b else None,
        "history":    state.history,
        "queue":      state.queue,
        "ref_bpm":    state.ref_bpm,
        "script":     script_summary,
        "error":      state.error,
    })


@app.post("/api/dj/{dj_id}/queue")
async def dj_enqueue(dj_id: str, body: dict):
    state = _dj_store.get(dj_id)
    if not state:
        return JSONResponse({"error": "dj session not found"}, status_code=404)
    h = body.get("hash") or body.get("path")
    resolved = _library.resolve(h) if h else None
    if not resolved:
        return JSONResponse({"error": "track not in library"}, status_code=400)
    state.queue.append(resolved)
    return {"queued": resolved, "queue_length": len(state.queue)}


# ── Shutdown ──────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def _shutdown() -> None:
    for sess in _audio_store.values():
        if sess.scheduler is not None:
            await sess.scheduler.stop()


# ── Static frontend ───────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")
```

- [ ] **Step 2: Verify server.py imports and starts cleanly**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "import server; print('ok')"
```

Expected: `ok` (no import errors)

- [ ] **Step 3: Verify health endpoint responds**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && uvicorn server:app --port 8001 &
sleep 2
curl -s http://127.0.0.1:8001/health
kill %1
```

Expected: `{"ok":true}`

- [ ] **Step 4: Run all existing tests to confirm nothing broke**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/ -v
```

Expected: `3 passed` (test_library × 9 + test_executor × 2 — all pass)

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/server.py && git commit -m "feat(backend): server.py routes-only refactor, delete legacy endpoints"
```

---

### Task 11: tests/test_normalizer.py — Normalizer test suite

**Files:**
- Create: `claude-dj/tests/test_normalizer.py`

- [ ] **Step 1: Create test_normalizer.py**

```python
# claude-dj/tests/test_normalizer.py
import pytest

from normalizer import _snap_duration_to_phrase, normalize
from schema import MixAction, MixScript, MixTrackRef


def _script(actions: list[MixAction], n_tracks: int = 2) -> MixScript:
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=128.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


def test_duration_clamped_min_4_bars():
    s = _script([MixAction(type="fade_in", track="T1", start_bar=0, duration_bars=2)])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in")
    assert fi.duration_bars >= 4


def test_duration_clamped_max_64_bars():
    s = _script([MixAction(type="fade_in", track="T1", start_bar=0, duration_bars=100)])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in")
    assert fi.duration_bars <= 64


def test_phrase_snap_13_becomes_16():
    assert _snap_duration_to_phrase(13) == 16


def test_phrase_snap_5_becomes_8():
    assert _snap_duration_to_phrase(5) == 8


def test_bass_swap_injected_when_missing():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0, from_bar=0),
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16, from_bar=0),
        MixAction(type="play",     track="T2", at_bar=48, from_bar=16),
    ])
    result = normalize(s)
    swaps = [a for a in result.actions if a.type == "bass_swap"]
    assert len(swaps) == 1
    assert swaps[0].track == "T1"
    assert swaps[0].incoming_track == "T2"


def test_incoming_track_backfilled_on_existing_bass_swap():
    s = _script([
        MixAction(type="play",      track="T1", at_bar=0, from_bar=0),
        MixAction(type="fade_out",  track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",   track="T2", start_bar=32, duration_bars=16, from_bar=0),
        MixAction(type="play",      track="T2", at_bar=48, from_bar=16),
        MixAction(type="bass_swap", track="T1", at_bar=40),   # no incoming_track
    ])
    result = normalize(s)
    swaps = [a for a in result.actions if a.type == "bass_swap"]
    assert len(swaps) == 1
    assert swaps[0].incoming_track == "T2"


def test_orphaned_fade_in_gets_injected_play():
    s = _script([
        MixAction(type="fade_in", track="T1", start_bar=0, from_bar=0, duration_bars=16),
        # no play follows
    ], n_tracks=1)
    result = normalize(s)
    plays = [a for a in result.actions if a.type == "play" and a.track == "T1"]
    assert len(plays) == 1
    assert plays[0].at_bar == 16   # start_bar + duration_bars


def test_three_track_set_two_bass_swaps():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16, from_bar=0),
        MixAction(type="play",     track="T2", at_bar=48, from_bar=16),
        MixAction(type="fade_out", track="T2", start_bar=80, duration_bars=16),
        MixAction(type="fade_in",  track="T3", start_bar=80, duration_bars=16, from_bar=0),
        MixAction(type="play",     track="T3", at_bar=96, from_bar=16),
    ], n_tracks=3)
    result = normalize(s)
    swaps = [a for a in result.actions if a.type == "bass_swap"]
    assert len(swaps) == 2
    tracks_cut     = {s.track          for s in swaps}
    tracks_restore = {s.incoming_track for s in swaps}
    assert "T1" in tracks_cut
    assert "T2" in tracks_cut
    assert "T2" in tracks_restore
    assert "T3" in tracks_restore
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_normalizer.py -v
```

Expected: `8 passed`

- [ ] **Step 3: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/tests/test_normalizer.py && git commit -m "test(backend): test_normalizer.py — duration clamping, phrase snapping, bass_swap injection"
```

---

### Task 12: tests/test_executor.py — Complete executor test suite

**Files:**
- Modify: `claude-dj/tests/test_executor.py` (add compute_cursors tests)

- [ ] **Step 1: Append cursor tests to test_executor.py**

```python
def test_compute_cursors_play_sets_active():
    ref_bpm = 128.0
    script  = _script([MixAction(type="play", track="T1", at_bar=0, from_bar=0)])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(4, ref_bpm))
    assert cursors["T1"].active is True


def test_compute_cursors_fade_in_sets_active():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="fade_in", track="T1", start_bar=0, from_bar=0, duration_bars=8),
    ])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(4, ref_bpm))
    assert cursors["T1"].active is True
    assert cursors["T1"].fade_in_start_ms == 0


def test_compute_cursors_bass_cut_after_bass_swap():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="play",      track="T1", at_bar=0, from_bar=0),
        MixAction(type="bass_swap", track="T1", at_bar=8),
    ])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(10, ref_bpm))
    assert cursors["T1"].bass_cut is True


def test_compute_cursors_bass_restored_on_incoming():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_in",   track="T2", start_bar=8, duration_bars=8, from_bar=0),
        MixAction(type="bass_swap", track="T1", at_bar=12, incoming_track="T2"),
    ], n_tracks=2)
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(14, ref_bpm))
    assert cursors["T1"].bass_cut is True
    assert cursors["T2"].bass_cut is False
```

- [ ] **Step 2: Run full test_executor.py**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_executor.py -v
```

Expected: `6 passed`

- [ ] **Step 3: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/tests/test_executor.py && git commit -m "test(backend): test_executor.py — equal-power, cursors, render_chunk"
```

---

### Task 13: tests/test_dsp.py — DSP test suite

**Files:**
- Create: `claude-dj/tests/test_dsp.py`

- [ ] **Step 1: Create test_dsp.py**

```python
# claude-dj/tests/test_dsp.py
import numpy as np
import pytest
from pydub import AudioSegment

from executor import (
    TARGET_DBFS,
    _apply_smooth_bass_swap,
    _apply_soft_limiter,
    apply_loudness_match,
    bars_to_ms,
)


def _mono(samples_int16: np.ndarray, rate: int = 44100) -> AudioSegment:
    return AudioSegment(
        samples_int16.tobytes(), frame_rate=rate, sample_width=2, channels=1,
    )


def _hot_audio(db_over: float = 6, ms: int = 500, rate: int = 44100) -> AudioSegment:
    """White noise driven db_over dB above 0 dBFS."""
    max_val = float(1 << 15)
    n = int(rate * ms / 1000)
    rng = np.random.default_rng(0)
    noise = (rng.random(n) * 2 - 1) * max_val * (10 ** (db_over / 20))
    return _mono(np.clip(noise, -max_val, max_val - 1).astype(np.int16), rate)


def test_soft_limiter_output_within_unit_range():
    audio   = _hot_audio(db_over=6)
    limited = _apply_soft_limiter(audio)
    max_val = float(1 << 15)
    samples = np.array(limited.get_array_of_samples(), dtype=np.float32) / max_val
    assert np.all(samples >= -1.0), f"min={samples.min():.4f}"
    assert np.all(samples <=  1.0), f"max={samples.max():.4f}"


def test_loudness_match_rms_within_half_db_of_target():
    rate    = 44100
    max_val = float(1 << 15)
    t       = np.linspace(0, 1.0, rate, dtype=np.float32)
    gain    = 10 ** (-8.0 / 20)      # -8 dBFS source
    tone    = (np.sin(2 * np.pi * 440 * t) * max_val * gain).astype(np.int16)
    audio   = _mono(tone, rate)

    matched = apply_loudness_match(audio, -8.0)
    samples = np.array(matched.get_array_of_samples(), dtype=np.float32) / max_val
    rms_db  = 20 * np.log10(np.sqrt(np.mean(samples ** 2)) + 1e-9)
    assert abs(rms_db - TARGET_DBFS) < 0.5, f"rms_db={rms_db:.2f}, target={TARGET_DBFS}"


def test_loudness_match_skips_when_within_threshold():
    rate    = 44100
    max_val = float(1 << 15)
    gain    = 10 ** (TARGET_DBFS / 20)
    tone    = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, rate)) * max_val * gain).astype(np.int16)
    audio   = _mono(tone, rate)

    result = apply_loudness_match(audio, TARGET_DBFS)
    # Within 0.5 dB threshold → returned unchanged
    assert result is audio


def test_smooth_bass_swap_no_large_discontinuity():
    """No sample-to-sample jump > 3× local RMS in a window around the swap point."""
    rate    = 44100
    max_val = float(1 << 15)
    rng     = np.random.default_rng(1)
    n       = rate * 4   # 4 seconds
    noise   = (rng.random(n) * 2 - 1) * max_val * 0.5
    audio   = _mono(noise.astype(np.int16), rate)

    ref_bpm = 128.0
    swap_ms = bars_to_ms(4, ref_bpm)
    result  = _apply_smooth_bass_swap(audio, swap_ms, ref_bpm)

    samples    = np.array(result.get_array_of_samples(), dtype=np.float32)
    swap_sample = int(swap_ms * rate / 1000)
    # Check 200 ms window centred on swap point
    w_start    = max(0, swap_sample - int(0.1 * rate))
    w_end      = min(len(samples), swap_sample + int(0.1 * rate))
    window     = samples[w_start:w_end]
    local_rms  = np.sqrt(np.mean(window ** 2))

    if local_rms > 0:
        diffs = np.abs(np.diff(window))
        assert np.all(diffs < local_rms * 3), \
            f"Max diff {diffs.max():.1f} exceeds 3× local RMS {local_rms:.1f}"
```

- [ ] **Step 2: Run test_dsp.py**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_dsp.py -v
```

Expected: `4 passed`

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/ -v
```

Expected: `23 passed` (9 library + 6 executor + 8 normalizer + 4 dsp)

- [ ] **Step 4: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/tests/test_dsp.py && git commit -m "test(backend): test_dsp.py — soft limiter, loudness match, smooth bass swap"
```

---

## Self-review

**Spec coverage:**
- ✅ state.py — Task 1
- ✅ library.py — Task 2
- ✅ dj_session.py — Task 3
- ✅ Equal-power crossfades — Task 4
- ✅ Render parity — Task 5
- ✅ Smooth bass swap — Task 6
- ✅ Loop boundary crossfade — Task 7
- ✅ Soft limiter — Task 8
- ✅ EQ shelving — Task 9
- ✅ Loudness matching (`apply_loudness_match` + `TARGET_DBFS`) — Task 3 (added to executor.py as prerequisite for dj_session.py)
- ✅ server.py routes-only — Task 10
- ✅ Delete `/api/analyze`, `/api/analyze/{job_id}`, `/api/plan` — Task 10
- ✅ test_normalizer.py — Task 11
- ✅ test_executor.py — Tasks 4+8+12
- ✅ test_library.py — Task 2
- ✅ test_dsp.py — Task 13
- ✅ API contract unchanged (same endpoint signatures) — Task 10

**Type consistency:**
- `Library.upsert(hash, LibraryEntry)` defined Task 2, called Task 10 ✅
- `dj_worker(dj_id, dj_store, audio_store, library)` defined Task 3, called Task 10 ✅
- `DjDeckA`, `DjDeckB`, `DjSessionState` defined Task 1, used Task 3 + Task 10 ✅
- `AudioSession` defined Task 1, used Task 3 ✅
- `apply_loudness_match(seg, source_dbfs)` defined Task 3/executor, used Task 3/dj_session ✅
- `_apply_smooth_bass_swap(layer, swap_ms, ref_bpm)` defined Task 6, tested Task 13 ✅
- `_apply_soft_limiter(canvas)` defined Task 8, tested Task 13 ✅
