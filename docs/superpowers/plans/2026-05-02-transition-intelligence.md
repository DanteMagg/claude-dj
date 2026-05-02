# Transition Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add vocal-aware zone analysis, a per-track MixingProfile computed once at analysis time, and richer "because"-flavored derived hints so the DJ model receives interpretations instead of raw data.

**Architecture:** Phase 0 adds `build_mixing_profile()` to `analyze_track()`, which computes vocal regions / loop candidates / transition windows algorithmically then makes one Haiku API call for `dj_notes`. Zone enrichment adds a `vocals` column and semantic `tags` list to every bar row. `_compute_zone_hints()` is rewritten to produce vocal sequencing, bass swap "because", loop candidates, and technique recommendation blocks. `_vocal_warning()` is removed (superseded). Phase 1 (`select_transition_window`) gains a mixing profile summary injection slot.

**Tech Stack:** Python 3.12, librosa, numpy, anthropic SDK, pytest, dataclasses

---

## Task 1: schema.py — New dataclasses + mixing_profile field

**Files:**
- Modify: `claude-dj/schema.py`

- [ ] **Step 1: Write the failing test**

```python
# claude-dj/tests/test_schema_mixing_profile.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schema import LoopCandidate, MixingProfile, TrackAnalysis, TransitionWindow


def test_loop_candidate_fields():
    lc = LoopCandidate(start_bar=80, bars=8, reason="drums-only, h=0.04")
    assert lc.start_bar == 80
    assert lc.bars == 8
    assert lc.reason == "drums-only, h=0.04"


def test_transition_window_fields():
    tw = TransitionWindow(bar=96, quality=9, character="drums-only 16 bars")
    assert tw.bar == 96
    assert tw.quality == 9
    assert tw.character == "drums-only 16 bars"


def test_mixing_profile_fields():
    profile = MixingProfile(
        vocal_bars=[(16, 48), (64, 80)],
        loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason="clean")],
        transition_windows=[TransitionWindow(bar=96, quality=9, character="drums-only")],
        intro_type="drums-only",
        outro_type="drums-only",
        dj_notes="Clean outro from bar 96.",
    )
    assert profile.intro_type == "drums-only"
    assert len(profile.vocal_bars) == 2
    assert len(profile.loop_candidates) == 1


def test_track_analysis_mixing_profile_defaults_none():
    from schema import BarGrid, CuePoint, KeyInfo, Section, SectionStems, StemPresence, StemPaths
    key = KeyInfo(camelot="8B", standard="C major", mode="major", tonic="C")
    stem = StemPresence(presence=0, rms_db=-80.0)
    stems = SectionStems(drums=stem, bass=stem, vocals=stem, other=stem)
    section = Section(
        label="groove", start_bar=0, end_bar=16, start_s=0.0, end_s=30.0,
        energy=5, loudness_dbfs=-12.0, stems=stems,
    )
    a = TrackAnalysis(
        id="T1", title="Test", artist="A", file="/t.mp3",
        duration_s=120.0, bpm=128.0, first_downbeat_s=0.0,
        key=key, energy_overall=5, loudness_dbfs=-12.0,
        bar_grid=BarGrid(n_bars=64, beats_per_bar=4),
        energy_curve_per_bar="5" * 64,
        sections=[section],
        cue_points=[CuePoint(name="mix_in", bar=0, type="phrase_start")],
        stems=StemPaths(vocals="", drums="", bass="", other=""),
    )
    assert a.mixing_profile is None


def test_mixing_profile_survives_asdict_roundtrip():
    import dataclasses
    from schema import LoopCandidate, MixingProfile, TransitionWindow
    profile = MixingProfile(
        vocal_bars=[(4, 8)],
        loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason="clean")],
        transition_windows=[TransitionWindow(bar=80, quality=8, character="drums-only")],
        intro_type="drums-only",
        outro_type="fade-silence",
        dj_notes="Test notes.",
    )
    # asdict converts tuples to lists — verify it doesn't blow up
    d = dataclasses.asdict(profile)
    assert d["intro_type"] == "drums-only"
    assert d["vocal_bars"] == [[4, 8]]  # tuples become lists
    assert d["loop_candidates"][0]["bars"] == 8
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_schema_mixing_profile.py -v 2>&1 | head -30
```
Expected: `ImportError: cannot import name 'LoopCandidate' from 'schema'`

- [ ] **Step 3: Implement in schema.py**

Add after the `CuePoint` dataclass (before `BarGrid`):

```python
@dataclass
class LoopCandidate:
    start_bar: int
    bars: int       # snapped to valid: 2, 4, 8, 16
    reason: str


@dataclass
class TransitionWindow:
    bar: int
    quality: int    # 1–10
    character: str  # "drums-only" | "breakdown" | "sparse-melodic"


@dataclass
class MixingProfile:
    vocal_bars: list            # list of [start_bar, end_bar] pairs
    loop_candidates: list       # list of LoopCandidate, best first
    transition_windows: list    # list of TransitionWindow, best first
    intro_type: str             # "drums-only" | "melodic" | "instant-drop" | "silent"
    outro_type: str             # "drums-only" | "cold-stop" | "vocals-to-end" | "fade-silence"
    dj_notes: str
```

Add `mixing_profile` field at the end of `TrackAnalysis` (after `stems`):

```python
    mixing_profile: Optional[MixingProfile] = None
```

The `Optional` import is already present. `list` type hints are left unparameterized intentionally so the dataclass accepts both tuples and lists from deserialized JSON.

- [ ] **Step 4: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_schema_mixing_profile.py -v
```
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/schema.py claude-dj/tests/test_schema_mixing_profile.py && git commit -m "feat(schema): add LoopCandidate, TransitionWindow, MixingProfile; add mixing_profile to TrackAnalysis"
```

---

## Task 2: analyze.py — Pure tag helpers (testable without file I/O)

**Files:**
- Modify: `claude-dj/analyze.py`
- Create: `claude-dj/tests/test_zone_enrichment.py`

The zone enrichment and profile computation share tag logic. Extract `_assign_tags()` and `_build_vocal_regions()` as pure functions at the module level so tests can import them directly.

- [ ] **Step 1: Write the failing tests**

```python
# claude-dj/tests/test_zone_enrichment.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyze import _assign_tags, _build_vocal_regions


# ── _assign_tags ────────────────────────────────────────────────────────────

def test_loop_safe_tag():
    tags = _assign_tags(drums=0.60, harmonic=0.05, vocals=0.10)
    assert "LOOP_SAFE" in tags
    assert "LOOP_UNSAFE_VOX" not in tags
    assert "LOOP_UNSAFE_HARM" not in tags


def test_vocal_active_and_loop_unsafe_vox():
    tags = _assign_tags(drums=0.60, harmonic=0.05, vocals=0.50)
    assert "VOCAL_ACTIVE" in tags
    assert "LOOP_UNSAFE_VOX" in tags
    assert "LOOP_SAFE" not in tags


def test_loop_unsafe_harm():
    tags = _assign_tags(drums=0.60, harmonic=0.20, vocals=0.05)
    assert "LOOP_UNSAFE_HARM" in tags
    assert "LOOP_SAFE" not in tags


def test_fade_in_ok():
    tags = _assign_tags(drums=0.60, harmonic=0.10, vocals=0.05)
    assert "FADE_IN_OK" in tags


def test_fade_in_not_ok_when_vocals_present():
    tags = _assign_tags(drums=0.60, harmonic=0.10, vocals=0.35)
    assert "FADE_IN_OK" not in tags


def test_no_tags_for_ambiguous_bar():
    # drums too low for LOOP_SAFE/FADE_IN_OK, vocals not high enough for VOCAL_ACTIVE
    tags = _assign_tags(drums=0.10, harmonic=0.05, vocals=0.05)
    assert tags == []


def test_loop_safe_and_fade_in_ok_coexist():
    # both conditions met simultaneously
    tags = _assign_tags(drums=0.60, harmonic=0.05, vocals=0.05)
    assert "LOOP_SAFE" in tags
    assert "FADE_IN_OK" in tags


# ── _build_vocal_regions ────────────────────────────────────────────────────

def test_vocal_regions_empty_when_all_silent():
    regions = _build_vocal_regions([0.0] * 20)
    assert regions == []


def test_vocal_regions_single_contiguous():
    # bars 4–6 active (indices 4, 5, 6 out of 0-indexed)
    rms = [0.0] * 4 + [0.5, 0.5, 0.5] + [0.0] * 3
    regions = _build_vocal_regions(rms)
    assert regions == [(4, 6)]


def test_vocal_regions_two_separate():
    rms = [0.0, 0.5, 0.0, 0.5, 0.5, 0.0]
    regions = _build_vocal_regions(rms)
    assert regions == [(1, 1), (3, 4)]


def test_vocal_regions_threshold_boundary():
    # exactly at threshold — 0.30 is NOT active (> 0.30 required)
    rms = [0.30, 0.31, 0.30]
    regions = _build_vocal_regions(rms)
    assert regions == [(1, 1)]


def test_vocal_regions_active_to_end():
    rms = [0.0, 0.5, 0.5]
    regions = _build_vocal_regions(rms)
    assert regions == [(1, 2)]
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_zone_enrichment.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name '_assign_tags' from 'analyze'`

- [ ] **Step 3: Add the two pure helpers to analyze.py**

Add after the `ANALYSIS_SR` / `MAX_ANALYSIS_SECONDS` constants block (before `file_hash`):

```python
# ── Tag thresholds ────────────────────────────────────────────────────────────
_VOC_ACTIVE_THRESH   = 0.30
_HARM_SAFE_THRESH    = 0.10
_VOC_SAFE_THRESH     = 0.20
_DRUM_ACTIVE_THRESH  = 0.25
_HARM_FADE_THRESH    = 0.20


def _assign_tags(drums: float, harmonic: float, vocals: float) -> list[str]:
    """Return semantic tags for a single bar given its stem RMS values (0–1)."""
    tags: list[str] = []
    if vocals > _VOC_ACTIVE_THRESH:
        tags.append("VOCAL_ACTIVE")

    loop_safe = harmonic < _HARM_SAFE_THRESH and vocals < _VOC_SAFE_THRESH and drums > _DRUM_ACTIVE_THRESH
    if loop_safe:
        tags.append("LOOP_SAFE")
    else:
        if vocals > _VOC_ACTIVE_THRESH:
            tags.append("LOOP_UNSAFE_VOX")
        if harmonic > 0.15:
            tags.append("LOOP_UNSAFE_HARM")

    if drums > _DRUM_ACTIVE_THRESH and harmonic < _HARM_FADE_THRESH and vocals < _VOC_SAFE_THRESH:
        tags.append("FADE_IN_OK")

    return tags


def _build_vocal_regions(normalized_rms_by_bar: list[float]) -> list[tuple[int, int]]:
    """
    Given per-bar normalized vocal RMS (0–1), return a list of (start_bar, end_bar)
    tuples covering contiguous runs where vocal > _VOC_ACTIVE_THRESH.
    """
    regions: list[tuple[int, int]] = []
    in_region = False
    region_start = 0
    for i, v in enumerate(normalized_rms_by_bar):
        if v > _VOC_ACTIVE_THRESH and not in_region:
            in_region = True
            region_start = i
        elif v <= _VOC_ACTIVE_THRESH and in_region:
            in_region = False
            regions.append((region_start, i - 1))
    if in_region:
        regions.append((region_start, len(normalized_rms_by_bar) - 1))
    return regions
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_zone_enrichment.py -v
```
Expected: all 12 PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/analyze.py claude-dj/tests/test_zone_enrichment.py && git commit -m "feat(analyze): add _assign_tags + _build_vocal_regions helpers; zone enrichment tests"
```

---

## Task 3: analyze_transition_zone() — vocals column + tags

**Files:**
- Modify: `claude-dj/analyze.py` (extend `analyze_transition_zone()`)

- [ ] **Step 1: Add integration-style test to test_zone_enrichment.py**

Append to `claude-dj/tests/test_zone_enrichment.py`:

```python
# ── analyze_transition_zone row schema ──────────────────────────────────────

def test_zone_row_has_vocals_key(tmp_path):
    """Zone rows always have a 'vocals' key (0.0 when no stem available)."""
    import numpy as np
    import soundfile as sf
    from analyze import analyze_transition_zone

    # 10-second sine wave at 128 BPM → roughly 5 bars
    sr = 22050
    duration = 10.0
    t = np.linspace(0, duration, int(sr * duration))
    audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    audio_path = str(tmp_path / "test.wav")
    sf.write(audio_path, audio, sr)

    rows = analyze_transition_zone(audio_path, bpm=128.0, first_downbeat_s=0.0, start_bar=0, n_bars=4)
    assert len(rows) > 0
    for row in rows:
        assert "vocals" in row
        assert row["vocals"] == 0.0  # no stems cached → fallback
        assert "tags" in row
        assert isinstance(row["tags"], list)


def test_zone_row_has_all_original_keys(tmp_path):
    import numpy as np
    import soundfile as sf
    from analyze import analyze_transition_zone

    sr = 22050
    t = np.linspace(0, 10.0, int(sr * 10.0))
    audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    audio_path = str(tmp_path / "test.wav")
    sf.write(audio_path, audio, sr)

    rows = analyze_transition_zone(audio_path, bpm=128.0, first_downbeat_s=0.0, start_bar=0, n_bars=2)
    for row in rows:
        for key in ("bar", "drums", "harmonic", "rms", "brightness", "onsets"):
            assert key in row
```

- [ ] **Step 2: Run to confirm baseline (should fail on missing vocals/tags keys)**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_zone_enrichment.py::test_zone_row_has_vocals_key -v 2>&1 | tail -10
```
Expected: `AssertionError: assert 'vocals' in {...}`

- [ ] **Step 3: Extend analyze_transition_zone() to load vocal stem and populate vocals + tags**

In `analyze.py`, inside `analyze_transition_zone()`, add vocal stem loading after the existing stem loading block (after `has_stems = drums_stem_path.exists() and bass_stem_path.exists()`):

```python
    # ── Vocal stem (optional — added alongside drums/harmonic) ───────────────
    vocals_stem_path = cache_dir / "stems" / "vocals.wav"
    has_vocals = vocals_stem_path.exists()
    vocals_y: Optional[np.ndarray] = None
    if has_vocals:
        vocals_y, _ = librosa.load(
            str(vocals_stem_path), sr=ANALYSIS_SR, mono=True,
            offset=max(0.0, zone_start_s), duration=zone_dur_s,
        )
        # Trim to match y_full length (which may have been trimmed by harm_len above)
        if vocals_y is not None and len(vocals_y) > len(y_full):
            vocals_y = vocals_y[:len(y_full)]

    voc_peak = float(np.sqrt(np.mean(vocals_y ** 2))) + 1e-9 if vocals_y is not None else 1.0
```

Note: The `vocals_y` trim must go *after* the `y_full = y_full[:harm_len]` reassignment. Replace the variable declarations at the top of the HPSS/stem-loading block to also trim vocals:

In the `if has_stems:` block, after `y_full = y_full[:harm_len]`, add:
```python
        if vocals_y is not None and len(vocals_y) > len(y_full):
            vocals_y = vocals_y[:len(y_full)]
```

Then in the per-bar loop, after computing `drum_rms`, `harm_rms`, add:

```python
        # Vocal RMS — normalised to vocal zone peak
        if vocals_y is not None and s < len(vocals_y):
            voc_slice = vocals_y[s:e]
            voc_rms = float(np.sqrt(np.mean(voc_slice ** 2))) / voc_peak if len(voc_slice) > 0 else 0.0
        else:
            voc_rms = 0.0

        tags = _assign_tags(
            drums=round(min(1.0, drum_rms * 1.5), 2),
            harmonic=round(min(1.0, harm_rms * 1.5), 2),
            vocals=round(min(1.0, voc_rms), 2),
        )
```

And update the `results.append()` call to include the new fields:

```python
        results.append({
            "bar":        bar_abs,
            "drums":      round(min(1.0, drum_rms * 1.5), 2),
            "harmonic":   round(min(1.0, harm_rms * 1.5), 2),
            "brightness": round(brightness, 2),
            "onsets":     onsets,
            "rms":        round(min(1.0, mix_rms), 2),
            "vocals":     round(min(1.0, voc_rms), 2),
            "tags":       tags,
        })
```

- [ ] **Step 4: Run all zone enrichment tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_zone_enrichment.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/analyze.py claude-dj/tests/test_zone_enrichment.py && git commit -m "feat(analyze): extend analyze_transition_zone with vocals column and tags"
```

---

## Task 4: analyze.py — Profile computation helpers (pure, testable)

**Files:**
- Modify: `claude-dj/analyze.py`
- Create: `claude-dj/tests/test_mixing_profile.py`

Extract the algorithmic (no-API, no-I/O) profile computation into testable helpers before wiring them into `build_mixing_profile()`.

- [ ] **Step 1: Write the failing tests**

```python
# claude-dj/tests/test_mixing_profile.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyze import (
    _classify_intro,
    _classify_outro,
    _find_loop_candidates,
    _find_transition_windows,
)


# ── _classify_intro ─────────────────────────────────────────────────────────

def _bar(drums, harmonic, vocals, rms):
    return {"drums": drums, "harmonic": harmonic, "vocals": vocals, "rms": rms}


def test_intro_type_drums_only():
    bars = [_bar(0.60, 0.05, 0.05, 0.40)] * 8
    assert _classify_intro(bars) == "drums-only"


def test_intro_type_melodic():
    bars = [_bar(0.60, 0.40, 0.05, 0.40)] * 8
    assert _classify_intro(bars) == "melodic"


def test_intro_type_instant_drop():
    bars = [_bar(0.80, 0.60, 0.10, 0.70)] * 8
    assert _classify_intro(bars) == "instant-drop"


def test_intro_type_silent():
    bars = [_bar(0.00, 0.00, 0.00, 0.02)] * 8
    assert _classify_intro(bars) == "silent"


# ── _classify_outro ─────────────────────────────────────────────────────────

def test_outro_type_drums_only():
    bars = [_bar(0.60, 0.05, 0.05, 0.40)] * 16
    assert _classify_outro(bars) == "drums-only"


def test_outro_type_cold_stop():
    bars = [_bar(0.00, 0.00, 0.00, 0.02)] * 4
    assert _classify_outro(bars) == "cold-stop"


def test_outro_type_vocals_to_end():
    bars = [_bar(0.60, 0.20, 0.50, 0.45)] * 16
    assert _classify_outro(bars) == "vocals-to-end"


def test_outro_type_fade_silence():
    bars = [_bar(0.30, 0.20, 0.10, 0.20)] * 16
    assert _classify_outro(bars) == "fade-silence"


# ── _find_loop_candidates ───────────────────────────────────────────────────

def _make_bars(n, drums=0.70, harmonic=0.04, vocals=0.05, rms=0.40):
    return [{"bar": i, "drums": drums, "harmonic": harmonic,
             "vocals": vocals, "rms": rms} for i in range(n)]


def test_loop_candidates_found_in_clean_span():
    bars = _make_bars(16)
    candidates = _find_loop_candidates(bars)
    assert len(candidates) > 0
    assert candidates[0].bars in (2, 4, 8, 16)


def test_loop_candidates_empty_when_all_vocal():
    bars = _make_bars(16, vocals=0.80)
    candidates = _find_loop_candidates(bars)
    assert candidates == []


def test_loop_candidates_empty_when_harmonic_too_high():
    bars = _make_bars(16, harmonic=0.30)
    candidates = _find_loop_candidates(bars)
    assert candidates == []


def test_loop_candidate_bars_snapped_to_valid():
    # 5 consecutive safe bars → snapped to 4 (nearest valid)
    bars = _make_bars(5)
    candidates = _find_loop_candidates(bars)
    assert all(c.bars in (2, 4, 8, 16) for c in candidates)


def test_loop_candidates_max_five_returned():
    bars = _make_bars(64)
    candidates = _find_loop_candidates(bars)
    assert len(candidates) <= 5


# ── _find_transition_windows ─────────────────────────────────────────────────

def test_transition_windows_found_in_low_energy_span():
    bars = [{"bar": i, "drums": 0.60, "harmonic": 0.04,
             "vocals": 0.05, "rms": 0.25} for i in range(24)]
    windows = _find_transition_windows(bars)
    assert len(windows) > 0
    assert windows[0].quality > 0


def test_transition_windows_empty_when_high_rms():
    bars = [{"bar": i, "drums": 0.60, "harmonic": 0.04,
             "vocals": 0.05, "rms": 0.80} for i in range(24)]
    windows = _find_transition_windows(bars)
    assert windows == []


def test_transition_window_character_drums_only():
    bars = [{"bar": i, "drums": 0.60, "harmonic": 0.04,
             "vocals": 0.05, "rms": 0.25} for i in range(16)]
    windows = _find_transition_windows(bars)
    assert windows[0].character == "drums-only"


def test_transition_window_character_breakdown():
    bars = [{"bar": i, "drums": 0.10, "harmonic": 0.05,
             "vocals": 0.05, "rms": 0.10} for i in range(16)]
    windows = _find_transition_windows(bars)
    assert windows[0].character == "breakdown"


def test_transition_windows_max_three_returned():
    bars = [{"bar": i, "drums": 0.60, "harmonic": 0.04,
             "vocals": 0.05, "rms": 0.25} for i in range(64)]
    windows = _find_transition_windows(bars)
    assert len(windows) <= 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_mixing_profile.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name '_classify_intro' from 'analyze'`

- [ ] **Step 3: Add pure computation helpers to analyze.py**

Add after `_build_vocal_regions()`:

```python
_PROFILE_LOOP_BARS = (2, 4, 8, 16)
_RMS_LOW_THRESH    = 0.35   # transition window energy threshold


def _snap_profile_loop_bars(n: int) -> int:
    """Snap n to nearest valid loop bar length for MixingProfile candidates."""
    return min(_PROFILE_LOOP_BARS, key=lambda v: (abs(v - n), -v))


def _classify_intro(first_bars: list[dict]) -> str:
    """Classify intro type from the first ≤8 bar-feature dicts."""
    if not first_bars:
        return "silent"
    window = first_bars[:8]
    avg_rms = sum(b["rms"] for b in window) / len(window)
    avg_drums = sum(b["drums"] for b in window) / len(window)
    avg_h = sum(b["harmonic"] for b in window) / len(window)
    avg_voc = sum(b["vocals"] for b in window) / len(window)

    if avg_rms < 0.10:
        return "silent"
    if avg_rms > 0.60:
        return "instant-drop"
    if avg_drums > _DRUM_ACTIVE_THRESH and avg_h < 0.15 and avg_voc < _VOC_SAFE_THRESH:
        return "drums-only"
    if avg_h > 0.20:
        return "melodic"
    return "silent"


def _classify_outro(last_bars: list[dict]) -> str:
    """Classify outro type from the last ≤16 bar-feature dicts."""
    if not last_bars:
        return "fade-silence"
    window = last_bars[-16:]
    tail = last_bars[-4:] if len(last_bars) >= 4 else last_bars

    # Cold stop: last 4 bars near-silent
    if all(b["rms"] < 0.05 for b in tail):
        return "cold-stop"

    # Vocals-to-end: any bar in last 16 has vocal activity
    if any(b["vocals"] > _VOC_ACTIVE_THRESH for b in window):
        return "vocals-to-end"

    avg_drums = sum(b["drums"] for b in window) / len(window)
    avg_h = sum(b["harmonic"] for b in window) / len(window)
    avg_voc = sum(b["vocals"] for b in window) / len(window)

    if avg_drums > 0.20 and avg_h < 0.15 and avg_voc < _VOC_SAFE_THRESH:
        return "drums-only"

    return "fade-silence"


def _find_loop_candidates(bar_features: list[dict]) -> list:
    """
    Find spans of 4+ consecutive LOOP_SAFE bars, snap to valid loop lengths,
    score, and return top 5 LoopCandidate objects ranked best first.
    """
    from schema import LoopCandidate

    safe_runs: list[tuple[int, int]] = []  # (start_idx, end_idx) inclusive
    in_run = False
    run_start = 0
    for i, b in enumerate(bar_features):
        is_safe = (
            b["harmonic"] < _HARM_SAFE_THRESH
            and b["vocals"] < _VOC_SAFE_THRESH
            and b["drums"] > _DRUM_ACTIVE_THRESH
        )
        if is_safe and not in_run:
            in_run, run_start = True, i
        elif not is_safe and in_run:
            in_run = False
            if i - run_start >= 4:
                safe_runs.append((run_start, i - 1))
    if in_run and len(bar_features) - run_start >= 4:
        safe_runs.append((run_start, len(bar_features) - 1))

    candidates: list[LoopCandidate] = []
    for start_idx, end_idx in safe_runs:
        span = end_idx - start_idx + 1
        snapped = _snap_profile_loop_bars(span)
        bars_slice = bar_features[start_idx : start_idx + snapped]
        if not bars_slice:
            continue
        avg_h   = sum(b["harmonic"] for b in bars_slice) / len(bars_slice)
        avg_voc = sum(b["vocals"]   for b in bars_slice) / len(bars_slice)
        avg_d   = sum(b["drums"]    for b in bars_slice) / len(bars_slice)
        score   = snapped - avg_h * 10 - avg_voc * 10  # longer + cleaner = higher score
        start_bar = bar_features[start_idx]["bar"]
        reason = (
            f"drums-only, h={avg_h:.2f}, vocals={avg_voc:.2f}, "
            f"drums={avg_d:.2f}, {snapped} bars clean"
        )
        candidates.append((score, LoopCandidate(start_bar=start_bar, bars=snapped, reason=reason)))

    candidates.sort(key=lambda x: -x[0])
    return [c for _, c in candidates[:5]]


def _find_transition_windows(bar_features: list[dict]) -> list:
    """
    Find spans of 8+ consecutive bars with rms < _RMS_LOW_THRESH and vocals < _VOC_SAFE_THRESH.
    Score and return top 3 TransitionWindow objects ranked best first.
    """
    from schema import TransitionWindow

    windows: list[tuple[float, TransitionWindow]] = []
    n = len(bar_features)
    i = 0
    while i < n:
        b = bar_features[i]
        if b["rms"] < _RMS_LOW_THRESH and b["vocals"] < _VOC_SAFE_THRESH:
            j = i + 1
            while j < n and bar_features[j]["rms"] < _RMS_LOW_THRESH and bar_features[j]["vocals"] < _VOC_SAFE_THRESH:
                j += 1
            span = j - i
            if span >= 8:
                window_bars = bar_features[i:j]
                avg_drums = sum(b2["drums"]    for b2 in window_bars) / span
                avg_h     = sum(b2["harmonic"] for b2 in window_bars) / span

                if avg_drums > _DRUM_ACTIVE_THRESH and avg_h < 0.15:
                    character = "drums-only"
                elif avg_drums < 0.15 and avg_h < 0.15:
                    character = "breakdown"
                else:
                    character = "sparse-melodic"

                quality = min(10, int(span / 2 + (1 - avg_h) * 5))
                score = quality + (1.0 if character == "drums-only" else 0.0)
                windows.append((score, TransitionWindow(
                    bar=bar_features[i]["bar"],
                    quality=quality,
                    character=character,
                )))
            i = j
        else:
            i += 1

    windows.sort(key=lambda x: -x[0])
    return [w for _, w in windows[:3]]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_mixing_profile.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/analyze.py claude-dj/tests/test_mixing_profile.py && git commit -m "feat(analyze): add profile computation helpers (_classify_intro/outro, _find_loop_candidates, _find_transition_windows)"
```

---

## Task 5: analyze.py — build_mixing_profile() + wire into analyze_track() + update _dict_to_analysis()

**Files:**
- Modify: `claude-dj/analyze.py`

- [ ] **Step 1: Add no-stems test to test_mixing_profile.py**

Append to `claude-dj/tests/test_mixing_profile.py`:

```python
def test_no_stems_returns_profile_with_empty_vocals():
    """build_mixing_profile with no_stems=True: vocal_bars empty, dj_notes contains stems note."""
    from unittest.mock import MagicMock, patch
    from analyze import build_mixing_profile
    from schema import StemPaths

    fake_bar_features = [
        {"bar": i, "drums": 0.60, "harmonic": 0.05, "vocals": 0.0, "rms": 0.25}
        for i in range(32)
    ]

    with patch("analyze._load_full_bar_features", return_value=fake_bar_features):
        profile = build_mixing_profile(
            audio_path="/fake/track.wav",
            bpm=128.0,
            first_downbeat_s=0.0,
            n_bars=32,
            stems=None,
            no_stems=True,
            title="Test Track",
            key_camelot="8B",
            duration_s=60.0,
            sections=[],
        )
    assert profile.vocal_bars == []
    assert "[stems unavailable" in profile.dj_notes


def test_dict_to_analysis_handles_missing_mixing_profile():
    """Old cache files without mixing_profile field deserialize cleanly."""
    import dataclasses, json
    from schema import BarGrid, CuePoint, KeyInfo, Section, SectionStems, StemPresence, StemPaths, TrackAnalysis
    from analyze import _dict_to_analysis

    key = KeyInfo(camelot="8B", standard="C major", mode="major", tonic="C")
    stem = StemPresence(presence=0, rms_db=-80.0)
    stems = SectionStems(drums=stem, bass=stem, vocals=stem, other=stem)
    section = Section(
        label="groove", start_bar=0, end_bar=16, start_s=0.0, end_s=30.0,
        energy=5, loudness_dbfs=-12.0, stems=stems,
    )
    a = TrackAnalysis(
        id="T1", title="Test", artist="A", file="/t.mp3",
        duration_s=120.0, bpm=128.0, first_downbeat_s=0.0,
        key=key, energy_overall=5, loudness_dbfs=-12.0,
        bar_grid=BarGrid(n_bars=64, beats_per_bar=4),
        energy_curve_per_bar="5" * 64,
        sections=[section],
        cue_points=[CuePoint(name="mix_in", bar=0, type="phrase_start")],
        stems=StemPaths(vocals="", drums="", bass="", other=""),
    )
    d = dataclasses.asdict(a)
    # Simulate old cache — no mixing_profile key
    d.pop("mixing_profile", None)
    result = _dict_to_analysis(d)
    assert result.mixing_profile is None


def test_dict_to_analysis_deserializes_mixing_profile():
    """Cached analysis with mixing_profile round-trips to MixingProfile object."""
    import dataclasses
    from schema import (
        BarGrid, CuePoint, KeyInfo, LoopCandidate, MixingProfile, Section,
        SectionStems, StemPresence, StemPaths, TrackAnalysis, TransitionWindow,
    )
    from analyze import _dict_to_analysis

    key = KeyInfo(camelot="8B", standard="C major", mode="major", tonic="C")
    stem = StemPresence(presence=0, rms_db=-80.0)
    stems_dc = SectionStems(drums=stem, bass=stem, vocals=stem, other=stem)
    section = Section(
        label="groove", start_bar=0, end_bar=16, start_s=0.0, end_s=30.0,
        energy=5, loudness_dbfs=-12.0, stems=stems_dc,
    )
    profile = MixingProfile(
        vocal_bars=[[4, 8]],
        loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason="clean")],
        transition_windows=[TransitionWindow(bar=80, quality=8, character="drums-only")],
        intro_type="drums-only",
        outro_type="fade-silence",
        dj_notes="Test.",
    )
    a = TrackAnalysis(
        id="T1", title="Test", artist="A", file="/t.mp3",
        duration_s=120.0, bpm=128.0, first_downbeat_s=0.0,
        key=key, energy_overall=5, loudness_dbfs=-12.0,
        bar_grid=BarGrid(n_bars=64, beats_per_bar=4),
        energy_curve_per_bar="5" * 64,
        sections=[section],
        cue_points=[CuePoint(name="mix_in", bar=0, type="phrase_start")],
        stems=StemPaths(vocals="", drums="", bass="", other=""),
        mixing_profile=profile,
    )
    d = dataclasses.asdict(a)
    result = _dict_to_analysis(d)
    assert result.mixing_profile is not None
    assert result.mixing_profile.intro_type == "drums-only"
    assert len(result.mixing_profile.loop_candidates) == 1
    assert result.mixing_profile.loop_candidates[0].bars == 8
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_mixing_profile.py::test_no_stems_returns_profile_with_empty_vocals tests/test_mixing_profile.py::test_dict_to_analysis_handles_missing_mixing_profile tests/test_mixing_profile.py::test_dict_to_analysis_deserializes_mixing_profile -v 2>&1 | tail -15
```
Expected: `ImportError: cannot import name 'build_mixing_profile'`

- [ ] **Step 3: Add _load_full_bar_features() helper to analyze.py**

This function loads all four stems for the full track and returns per-bar features. Add after `_find_transition_windows()`:

```python
def _load_full_bar_features(
    audio_path: str,
    bpm: float,
    first_downbeat_s: float,
    n_bars: int,
    stems: Optional[StemPaths],
) -> list[dict]:
    """
    Compute per-bar {drums, harmonic, vocals, rms} for the full track.
    Returns list of dicts indexed 0..n_bars-1. Uses Demucs stems if available,
    HPSS fallback otherwise.
    """
    secs_per_bar = 4 * 60.0 / bpm
    total_dur = n_bars * secs_per_bar

    # Load mix audio for RMS
    y_mix, sr = librosa.load(
        audio_path, sr=ANALYSIS_SR, mono=True,
        offset=first_downbeat_s, duration=total_dur,
    )
    if len(y_mix) == 0:
        return []

    cache_dir = CACHE_DIR / file_hash(audio_path)
    drums_path  = cache_dir / "stems" / "drums.wav"
    bass_path   = cache_dir / "stems" / "bass.wav"
    other_path  = cache_dir / "stems" / "other.wav"
    vocals_path = cache_dir / "stems" / "vocals.wav"

    has_demucs = stems is not None and drums_path.exists() and bass_path.exists()

    if has_demucs:
        y_drums, _ = librosa.load(str(drums_path),  sr=ANALYSIS_SR, mono=True,
                                   offset=first_downbeat_s, duration=total_dur)
        y_bass,  _ = librosa.load(str(bass_path),   sr=ANALYSIS_SR, mono=True,
                                   offset=first_downbeat_s, duration=total_dur)
        y_voc,   _ = librosa.load(str(vocals_path), sr=ANALYSIS_SR, mono=True,
                                   offset=first_downbeat_s, duration=total_dur) \
                     if vocals_path.exists() else (np.zeros_like(y_mix), sr)
        y_other, _ = librosa.load(str(other_path),  sr=ANALYSIS_SR, mono=True,
                                   offset=first_downbeat_s, duration=total_dur) \
                     if other_path.exists() else (np.zeros_like(y_mix), sr)
        min_len = min(len(y_mix), len(y_drums), len(y_bass))
        y_mix, y_drums, y_bass = y_mix[:min_len], y_drums[:min_len], y_bass[:min_len]
        y_other = y_other[:min_len] if len(y_other) >= min_len else np.pad(y_other, (0, min_len - len(y_other)))
        y_voc   = y_voc[:min_len]   if len(y_voc)   >= min_len else np.pad(y_voc,   (0, min_len - len(y_voc)))
        y_harm  = y_bass + y_other
    else:
        y_harm, y_drums = librosa.effects.hpss(y_mix, margin=3.0)
        y_voc = np.zeros_like(y_mix)

    mix_peak  = float(np.sqrt(np.mean(y_mix   ** 2))) + 1e-9
    drum_peak = float(np.sqrt(np.mean(y_drums ** 2))) + 1e-9
    harm_peak = float(np.sqrt(np.mean(y_harm  ** 2))) + 1e-9
    voc_peak  = float(np.sqrt(np.mean(y_voc   ** 2))) + 1e-9

    features: list[dict] = []
    for i in range(n_bars):
        s = int(i * secs_per_bar * sr)
        e = int((i + 1) * secs_per_bar * sr)
        if s >= len(y_mix):
            break
        e = min(e, len(y_mix))

        rms   = float(np.sqrt(np.mean(y_mix[s:e]   ** 2))) / mix_peak
        drums = float(np.sqrt(np.mean(y_drums[s:e]  ** 2))) / drum_peak
        harm  = float(np.sqrt(np.mean(y_harm[s:e]   ** 2))) / harm_peak
        voc   = float(np.sqrt(np.mean(y_voc[s:e]    ** 2))) / voc_peak

        # Apply same 1.5x boost for legibility as in analyze_transition_zone
        features.append({
            "bar":      i,
            "drums":    round(min(1.0, drums * 1.5), 3),
            "harmonic": round(min(1.0, harm  * 1.5), 3),
            "vocals":   round(min(1.0, voc),          3),
            "rms":      round(min(1.0, rms),           3),
        })
    return features
```

- [ ] **Step 4: Add build_mixing_profile() to analyze.py**

Add after `_load_full_bar_features()`. This requires `import anthropic` at the top of `analyze.py`. Add `import anthropic` to the imports block (place it after `from pydub import AudioSegment`).

```python
def build_mixing_profile(
    audio_path: str,
    bpm: float,
    first_downbeat_s: float,
    n_bars: int,
    stems: Optional[StemPaths],
    no_stems: bool,
    title: str,
    key_camelot: str,
    duration_s: float,
    sections: list,
) -> "MixingProfile":
    """
    Phase 0: compute a MixingProfile for a track once and cache it.
    Makes one claude-haiku API call (max 200 tokens) for dj_notes.
    """
    from schema import MixingProfile

    if no_stems or stems is None:
        # Still compute transition windows from mix audio RMS; skip vocal analysis
        bar_features = _load_full_bar_features(audio_path, bpm, first_downbeat_s, n_bars, None)
        vocal_bars: list = []
        loop_cands = []
        tw = _find_transition_windows(bar_features)
        intro = _classify_intro(bar_features[:8] if bar_features else [])
        outro = _classify_outro(bar_features[-16:] if bar_features else [])
        dj_notes = "[stems unavailable — vocal analysis skipped]"
        return MixingProfile(
            vocal_bars=vocal_bars,
            loop_candidates=loop_cands,
            transition_windows=tw,
            intro_type=intro,
            outro_type=outro,
            dj_notes=dj_notes,
        )

    bar_features = _load_full_bar_features(audio_path, bpm, first_downbeat_s, n_bars, stems)
    if not bar_features:
        return MixingProfile(
            vocal_bars=[], loop_candidates=[], transition_windows=[],
            intro_type="silent", outro_type="fade-silence",
            dj_notes="[analysis unavailable — no bar data]",
        )

    # Vocal map
    voc_rms_list = [b["vocals"] for b in bar_features]
    vocal_bars = _build_vocal_regions(voc_rms_list)

    loop_cands  = _find_loop_candidates(bar_features)
    tw          = _find_transition_windows(bar_features)
    intro       = _classify_intro(bar_features[:8])
    outro       = _classify_outro(bar_features[-16:])

    # API call for dj_notes
    section_summary = " ".join(
        f"{s.label}(b{s.start_bar}-{s.end_bar})" for s in sections
    ) if sections else "unknown"

    payload = {
        "title": title,
        "bpm": round(bpm, 1),
        "key": key_camelot,
        "duration_s": round(duration_s, 1),
        "section_summary": section_summary,
        "vocal_bars": [[s, e] for s, e in vocal_bars],
        "loop_candidates": [
            {"start_bar": lc.start_bar, "bars": lc.bars, "reason": lc.reason}
            for lc in loop_cands
        ],
        "transition_windows": [
            {"bar": tw_.bar, "quality": tw_.quality, "character": tw_.character}
            for tw_ in tw
        ],
        "intro_type": intro,
        "outro_type": outro,
    }

    dj_notes = "[dj_notes unavailable]"
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=(
                "You are a DJ reading a track before playing it. "
                "Given structured analysis data, write a concise mixing brief (3-5 sentences) "
                "describing: where vocals are active and what to avoid, the best transition-out "
                "window and why, any strong loop candidates, and one sentence on the track's "
                "overall character for mixing. Be specific about bar numbers."
            ),
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        dj_notes = resp.content[0].text.strip()
    except Exception as exc:
        print(f"  [build_mixing_profile] dj_notes API call failed ({exc}) — skipping")
        dj_notes = "[dj_notes unavailable]"

    return MixingProfile(
        vocal_bars=[[s, e] for s, e in vocal_bars],
        loop_candidates=loop_cands,
        transition_windows=tw,
        intro_type=intro,
        outro_type=outro,
        dj_notes=dj_notes,
    )
```

- [ ] **Step 5: Wire build_mixing_profile() into analyze_track()**

In `analyze_track()`, after `cue_points = _cue_points_from_sections(...)` and before `title = Path(audio_path).stem`, add:

```python
    # Phase 0: build mixing profile (cached; skip if already in analysis.json)
    mixing_profile = None
    if not no_stems and stem_paths is not None:
        try:
            print("  [analyze] building mixing profile (Phase 0)")
            from schema import MixingProfile as _MP  # avoid circular at module level
            mixing_profile = build_mixing_profile(
                audio_path=audio_path,
                bpm=bpm,
                first_downbeat_s=first_downbeat_s,
                n_bars=n_bars,
                stems=stem_paths,
                no_stems=no_stems,
                title=Path(audio_path).stem,
                key_camelot=key.camelot,
                duration_s=duration_s,
                sections=sections,
            )
        except Exception as exc:
            print(f"  [analyze] WARNING: build_mixing_profile failed ({exc}) — skipping")
```

Update the `TrackAnalysis(...)` construction to include `mixing_profile=mixing_profile`.

Also update the cache-load path at the top of `analyze_track()`. In the `if analysis_cache.exists():` block, the existing code loads and returns. The cache check for `"mixing_profile"` is already handled because:
- If `analysis.json` has `"mixing_profile"`, `_dict_to_analysis()` will deserialize it (see next step).
- Old caches without it get `mixing_profile=None` (OK per spec — user must delete cache).

- [ ] **Step 6: Update _dict_to_analysis() to deserialize MixingProfile**

Replace the final lines of `_dict_to_analysis()`:

```python
def _dict_to_analysis(d: dict) -> TrackAnalysis:
    d["key"] = KeyInfo(**d["key"])
    d["bar_grid"] = BarGrid(**d["bar_grid"])
    d["stems"] = StemPaths(**d["stems"])
    sections = []
    for s in d["sections"]:
        stems_d = s["stems"]
        for stem_name in stems_d:
            stems_d[stem_name] = StemPresence(**stems_d[stem_name])
        s["stems"] = SectionStems(**stems_d)
        sections.append(Section(**s))
    d["sections"] = sections
    d["cue_points"] = [CuePoint(**c) for c in d["cue_points"]]
    # migrate renamed field from old cache files
    if "loudness_lufs" in d:
        d["loudness_dbfs"] = d.pop("loudness_lufs")

    # Optional MixingProfile — absent in old caches
    profile_data = d.pop("mixing_profile", None)
    if profile_data:
        from schema import LoopCandidate, MixingProfile, TransitionWindow
        d["mixing_profile"] = MixingProfile(
            vocal_bars=profile_data.get("vocal_bars", []),
            loop_candidates=[
                LoopCandidate(**lc) for lc in profile_data.get("loop_candidates", [])
            ],
            transition_windows=[
                TransitionWindow(**tw) for tw in profile_data.get("transition_windows", [])
            ],
            intro_type=profile_data.get("intro_type", "silent"),
            outro_type=profile_data.get("outro_type", "fade-silence"),
            dj_notes=profile_data.get("dj_notes", ""),
        )

    return TrackAnalysis(**d)
```

- [ ] **Step 7: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_mixing_profile.py tests/test_schema_mixing_profile.py -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/analyze.py claude-dj/tests/test_mixing_profile.py && git commit -m "feat(analyze): add build_mixing_profile, _load_full_bar_features; wire Phase 0 into analyze_track; update _dict_to_analysis"
```

---

## Task 6: mix_director.py — _format_zone_table with vocals + tags

**Files:**
- Modify: `claude-dj/mix_director.py`

- [ ] **Step 1: Write failing test**

Create `claude-dj/tests/test_derived_hints.py`:

```python
# claude-dj/tests/test_derived_hints.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mix_director import _format_zone_table


def _row(bar, drums, harmonic, rms, brightness=0.40, onsets=2, vocals=0.0, tags=None):
    return {
        "bar": bar, "drums": drums, "harmonic": harmonic, "rms": rms,
        "brightness": brightness, "onsets": onsets,
        "vocals": vocals, "tags": tags or [],
    }


# ── _format_zone_table ──────────────────────────────────────────────────────

def test_zone_table_includes_vocals_column():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.08)]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "vox=0.08" in table


def test_zone_table_includes_tags():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.05, tags=["LOOP_SAFE"])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "[LOOP_SAFE]" in table


def test_zone_table_multiple_tags():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.50, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "[VOCAL_ACTIVE]" in table
    assert "[LOOP_UNSAFE_VOX]" in table


def test_zone_table_no_tags_row_clean():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.05, tags=[])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "vox=0.05" in table
    # No tag brackets should appear for this row
    assert "[" not in table or "exit zone" not in table.split("[")[0]
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py::test_zone_table_includes_vocals_column tests/test_derived_hints.py::test_zone_table_includes_tags -v 2>&1 | tail -10
```
Expected: `AssertionError` (vocals column not yet in table)

- [ ] **Step 3: Update _format_zone_table() in mix_director.py**

Replace the `_format_zone_table()` function:

```python
def _format_zone_table(zone: list[dict], track_id: str, label: str) -> str:
    if not zone:
        return f"{track_id} {label}: (no zone data)\n"

    first_bar = zone[0]["bar"]
    last_bar  = zone[-1]["bar"]
    lines = [f"{track_id} {label} (bars {first_bar}–{last_bar}):"]

    prev = None
    for row in zone:
        brightness = "bright" if row["brightness"] > 0.55 else ("mid" if row["brightness"] > 0.30 else "dark ")
        annotation = _annotate_bar(row, prev)
        vocals_val = row.get("vocals", 0.0)
        tags       = row.get("tags", [])
        tag_str    = "  " + " ".join(f"[{t}]" for t in tags) if tags else ""
        lines.append(
            f"  b{row['bar']:3d}: d={row['drums']:.2f} h={row['harmonic']:.2f} "
            f"r={row['rms']:.2f} {brightness} onsets={row['onsets']} "
            f"vox={vocals_val:.2f}{annotation}{tag_str}"
        )
        prev = row

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py::test_zone_table_includes_vocals_column tests/test_derived_hints.py::test_zone_table_includes_tags tests/test_derived_hints.py::test_zone_table_multiple_tags tests/test_derived_hints.py::test_zone_table_no_tags_row_clean -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/mix_director.py && git commit -m "feat(mix_director): add vocals column and tags to zone table display"
```

---

## Task 7: mix_director.py — Rewrite _compute_zone_hints, remove _vocal_warning, update callers

**Files:**
- Modify: `claude-dj/mix_director.py`

- [ ] **Step 1: Append failing tests to test_derived_hints.py**

```python
# --- Append to claude-dj/tests/test_derived_hints.py ---

from mix_director import _compute_zone_hints


def _make_zone(start_bar, n, drums=0.70, harmonic=0.05, rms=0.40, vocals=0.0, tags=None):
    rows = []
    for i in range(n):
        t = list(tags) if tags else []
        rows.append({
            "bar": start_bar + i, "drums": drums, "harmonic": harmonic,
            "rms": rms, "brightness": 0.4, "onsets": 2,
            "vocals": vocals, "tags": t,
        })
    return rows


# ── _compute_zone_hints (no profiles) ───────────────────────────────────────

def test_hints_returns_nonempty_string_for_zones():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert isinstance(result, str)
    assert len(result) > 0


def test_bass_swap_hint_present():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "bass_swap" in result.lower() or "preferred" in result.lower()


def test_bass_swap_has_because_clause():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "BECAUSE" in result


# ── _compute_zone_hints (with VOCAL_ACTIVE tags) ─────────────────────────────

def test_vocal_situation_block_present_when_vocals_in_t1():
    t1 = _make_zone(64, 16, vocals=0.50, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "VOCAL SITUATION" in result


def test_vocal_situation_shows_t1_last_vocal_bar():
    t1_zone = []
    for i in range(8):
        t1_zone.append({"bar": 64 + i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.5,
                        "tags": ["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"]})
    for i in range(8):
        t1_zone.append({"bar": 72 + i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.05,
                        "tags": ["LOOP_SAFE"]})
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1_zone, t2)
    assert "bar 71" in result or "b71" in result  # last vocal bar (0-indexed: 64+7=71)


def test_vocal_situation_shows_t2_vocal_entry():
    t1 = _make_zone(64, 16)
    t2_zone = []
    for i in range(4):
        t2_zone.append({"bar": i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.05, "tags": []})
    for i in range(4, 16):
        t2_zone.append({"bar": i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.50,
                        "tags": ["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"]})
    result = _compute_zone_hints(t1, t2_zone)
    assert "bar 4" in result or "b4" in result  # first T2 vocal bar


# ── Loop candidates block ────────────────────────────────────────────────────

def test_loop_candidates_block_present_when_loop_safe_bars():
    t1 = _make_zone(64, 16, tags=["LOOP_SAFE"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "LOOP CANDIDATES" in result


def test_loop_candidates_block_shows_unsafe():
    t1 = _make_zone(64, 16, vocals=0.5, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "LOOP_UNSAFE" in result or "LOOP CANDIDATES" in result


# ── Technique recommendation ─────────────────────────────────────────────────

def test_technique_recommendation_block_present():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "RECOMMENDED TECHNIQUE" in result


def test_technique_recommendation_has_avoid_clause():
    t1 = _make_zone(64, 16, vocals=0.5, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "AVOID" in result
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py -k "not zone_table" -v 2>&1 | tail -20
```
Expected: `AssertionError` on BECAUSE and VOCAL SITUATION checks

- [ ] **Step 3: Rewrite _compute_zone_hints() in mix_director.py**

Replace the entire `_compute_zone_hints()` function and remove `_vocal_warning()`:

```python
def _compute_zone_hints(
    t1_zone: list[dict],
    t2_zone: list[dict],
    t1_profile=None,
    t2_profile=None,
    t1: Optional[TrackAnalysis] = None,
    t2: Optional[TrackAnalysis] = None,
) -> str:
    """
    Derive concrete action targets from zone measurements and produce
    interpretive hint blocks so Claude reads decisions, not raw numbers.
    """
    blocks: list[str] = []

    # ── Vocal sequencing block ────────────────────────────────────────────────
    t1_vocal_bars = [r["bar"] for r in t1_zone if "VOCAL_ACTIVE" in r.get("tags", [])]
    t2_vocal_bars = [r["bar"] for r in t2_zone if "VOCAL_ACTIVE" in r.get("tags", [])]

    if t1_vocal_bars or t2_vocal_bars:
        vocal_lines = ["VOCAL SITUATION:"]
        if t1_vocal_bars:
            last_voc = max(t1_vocal_bars)
            eq_bar = last_voc - 4
            vocal_lines.append(f"  T1 vocals active until bar {last_voc} (last [VOCAL_ACTIVE] bar in T1 exit zone)")
            vocal_lines.append(f"  → eq(T1, bar={eq_bar}, mid=0.3) — cut T1 mids 4 bars before T1 vocals end")
            vocal_lines.append(f"  → Do NOT restore T1 mid — vocals would re-emerge into the blend")
        if t2_vocal_bars:
            first_voc = min(t2_vocal_bars)
            vocal_lines.append(f"  T2 vocals enter at bar {first_voc} (first [VOCAL_ACTIVE] bar in T2 entry zone)")
            vocal_lines.append(f"  → T1 mids must reach ≤ 0.3 before T2 bar {first_voc}")
            if t1_vocal_bars:
                t1_clear = max(t1_vocal_bars)
                safe_overlap = first_voc - (t1_clear - max(t1_zone, key=lambda r: r["bar"])["bar"] if t1_zone else 0)
                vocal_lines.append(f"  → Maximum safe overlap: ensure T1 vocal region ends before T2 reaches bar {first_voc}")
        blocks.append("\n".join(vocal_lines))

    # ── Bass swap block with BECAUSE clause ──────────────────────────────────
    if t1_zone:
        best_swap    = min(t1_zone, key=lambda r: r["drums"] + r["harmonic"])
        raw_bar      = best_swap["bar"]
        snap_bar     = round(raw_bar / 8) * 8
        snap_note    = f" (raw b{raw_bar} snapped to ×8)" if snap_bar != raw_bar else ""

        # Determine T1 section at swap bar
        t1_section_at_swap = ""
        if t1 is not None:
            for s in t1.sections:
                if s.start_bar <= snap_bar < s.end_bar:
                    t1_section_at_swap = f", T1 in {s.label.upper()} section"
                    break

        # T2 context
        t2_drums_only = [r for r in t2_zone if r["drums"] > 0.25 and r["harmonic"] < 0.20]
        t2_bass_entry = next((r for r in t2_zone if r["harmonic"] > 0.30), None)

        t2_context = ""
        if t2_drums_only:
            t2_context += f", T2 drums active b{t2_drums_only[0]['bar']}–b{t2_drums_only[-1]['bar']}"
        if t2_bass_entry:
            t2_context += f", T2 harmonic enters bar {t2_bass_entry['bar']}"

        # Vocal clearance note
        voc_clearance = ""
        t1_last_voc = max(t1_vocal_bars) if t1_vocal_bars else None
        t2_first_voc = min(t2_vocal_bars) if t2_vocal_bars else None
        if t1_last_voc is not None or t2_first_voc is not None:
            parts = []
            if t1_last_voc is not None:
                parts.append(f"T1 vocal end={t1_last_voc}")
            if t2_first_voc is not None:
                parts.append(f"T2 vocal start={t2_first_voc}")
            voc_clearance = f", vocals clear both sides ({', '.join(parts)})"

        dh_sum = best_swap["drums"] + best_swap["harmonic"]
        blocks.append(
            f"T1 preferred bass_swap: bar {snap_bar}{snap_note}\n"
            f"  BECAUSE: d+h={dh_sum:.2f} (lowest in exit zone)"
            f"{t1_section_at_swap}{t2_context}{voc_clearance}"
        )

    # ── Loop candidates block ────────────────────────────────────────────────
    if t1_zone:
        loop_lines = ["LOOP CANDIDATES in T1 exit zone:"]
        # Find runs of LOOP_SAFE bars
        safe_runs: list[list[int]] = []
        current: list[int] = []
        for r in t1_zone:
            if "LOOP_SAFE" in r.get("tags", []):
                current.append(r["bar"])
            else:
                if current:
                    safe_runs.append(current)
                    current = []
        if current:
            safe_runs.append(current)

        # Find unsafe spans
        unsafe_spans: list[dict] = []
        current_unsafe: list[dict] = []
        current_reason = ""
        for r in t1_zone:
            tags = r.get("tags", [])
            if "LOOP_UNSAFE_VOX" in tags:
                reason = "LOOP_UNSAFE_VOX"
            elif "LOOP_UNSAFE_HARM" in tags:
                reason = "LOOP_UNSAFE_HARM"
            else:
                reason = ""
            if reason:
                if reason == current_reason:
                    current_unsafe.append(r)
                else:
                    if current_unsafe:
                        unsafe_spans.append({"bars": current_unsafe, "reason": current_reason})
                    current_unsafe = [r]
                    current_reason = reason
            else:
                if current_unsafe:
                    unsafe_spans.append({"bars": current_unsafe, "reason": current_reason})
                    current_unsafe = []
                    current_reason = ""
        if current_unsafe:
            unsafe_spans.append({"bars": current_unsafe, "reason": current_reason})

        shown = 0
        for run in safe_runs[:2]:
            if not run:
                continue
            span_rows = [r for r in t1_zone if r["bar"] in run]
            avg_h   = sum(r["harmonic"] for r in span_rows) / len(span_rows)
            avg_voc = sum(r["vocals"]   for r in span_rows) / len(span_rows)
            avg_d   = sum(r["drums"]    for r in span_rows) / len(span_rows)
            loop_lines.append(
                f"  ✓ bars {run[0]}–{run[-1]}: LOOP_SAFE "
                f"(h={avg_h:.2f}, vocals={avg_voc:.2f}, drums={avg_d:.2f}) — "
                f"{len(run)} bars clean"
            )
            shown += 1

        for span in unsafe_spans[:2]:
            bars = span["bars"]
            if not bars:
                continue
            reason = span["reason"]
            avg_val = (
                sum(r["vocals"]   for r in bars) / len(bars) if "VOX"  in reason else
                sum(r["harmonic"] for r in bars) / len(bars)
            )
            detail = (
                f"vocals={avg_val:.2f} — active vocal, do not loop" if "VOX"  in reason else
                f"h={avg_val:.2f} — harmonic content present"
            )
            loop_lines.append(
                f"  ✗ bars {bars[0]['bar']}–{bars[-1]['bar']}: {reason} ({detail})"
            )

        if shown == 0 and not unsafe_spans:
            loop_lines.append("  (no LOOP_SAFE or LOOP_UNSAFE bars tagged in zone)")

        blocks.append("\n".join(loop_lines))

    # ── Technique recommendation block ────────────────────────────────────────
    rec_lines = ["RECOMMENDED TECHNIQUE:"]
    avoid_items: list[str] = []

    # Count clean T1 runway
    t1_clean_bars = [r for r in t1_zone if r.get("rms", 1.0) < 0.35 and r["vocals"] < 0.20]
    clean_runway = len(t1_clean_bars)

    # Camelot distance if tracks provided
    camelot_note = ""
    bpm_note = ""
    if t1 is not None and t2 is not None:
        try:
            dist = _camelot_distance(
                getattr(t1.key, "camelot", ""),
                getattr(t2.key, "camelot", ""),
            )
            camelot_note = f"Camelot dist={dist}"
            bpm_delta = abs(t1.bpm - t2.bpm)
            bpm_note = f"ΔBPM={bpm_delta:.1f}"
        except Exception:
            pass

    # Choose technique
    if clean_runway >= 16:
        technique = "blend"
        window = 32 if clean_runway >= 32 else 16
    else:
        technique = "cut"
        window = 8

    # Override if profile says instant-drop entry
    t2_intro_note = ""
    if t2_profile is not None:
        if t2_profile.intro_type == "instant-drop":
            technique = "cut"
            window = 8
            avoid_items.append("fade_in into instant-drop T2 entry (use cut instead)")
            t2_intro_note = "T2 instant-drop entry"
        elif t2_profile.intro_type == "drums-only":
            t2_intro_note = "T2 drums-only intro"

    reason_parts = []
    if clean_runway:
        reason_parts.append(f"T1 clean runway {clean_runway} bars")
    if camelot_note:
        reason_parts.append(camelot_note)
    if bpm_note:
        reason_parts.append(bpm_note)
    if t1_vocal_bars:
        reason_parts.append(f"T1 vocals end bar {max(t1_vocal_bars)}")
    if t2_intro_note:
        reason_parts.append(t2_intro_note)

    rec_lines.append(f"  {technique}, {window} bars")
    if reason_parts:
        rec_lines.append(f"  BECAUSE: {', '.join(reason_parts)}")

    # Avoid clauses
    if t1_vocal_bars or t2_vocal_bars:
        avoid_items.append("overlap with vocals at full mid level in either track")
    unsafe_tagged = [r["bar"] for r in t1_zone if any(
        t in r.get("tags", []) for t in ("LOOP_UNSAFE_VOX", "LOOP_UNSAFE_HARM")
    )]
    if unsafe_tagged:
        avoid_items.append(f"loop on [LOOP_UNSAFE_*] bars {unsafe_tagged[:4]}")

    if avoid_items:
        rec_lines.append("  AVOID: " + "; ".join(avoid_items))

    blocks.append("\n".join(rec_lines))

    if not blocks:
        return ""
    return (
        "DERIVED HINTS (computed from zone data — use as direct action targets):\n"
        + "\n\n".join(blocks)
        + "\n\n"
    )
```

- [ ] **Step 4: Remove _vocal_warning() and update _format_plan_prompt()**

Delete the entire `_vocal_warning()` function (lines from `def _vocal_warning(` to the closing `return "\n".join(lines) + "\n"`).

Update `_format_plan_prompt()` signature and body:

```python
def _format_plan_prompt(
    t1: TrackAnalysis,
    t2: TrackAnalysis,
    t1_zone: list[dict],
    t2_zone: list[dict],
    window: dict,
    concept: dict | None = None,
) -> str:
    summaries = (
        _format_track_summary(t1, "T1") + "\n\n" + _format_track_summary(t2, "T2")
    )
    t1_table = _format_zone_table(t1_zone, "T1", "exit zone")
    t2_table = _format_zone_table(t2_zone, "T2", "entry zone")

    zone_hints     = _compute_zone_hints(
        t1_zone, t2_zone,
        t1_profile=getattr(t1, "mixing_profile", None),
        t2_profile=getattr(t2, "mixing_profile", None),
        t1=t1, t2=t2,
    )
    retrieved_exs  = retrieve_examples(t1, t2, window, k=3, concept=concept)
    examples_block = _format_examples_block(retrieved_exs)

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

    coord_note = (
        "COORDINATE SYSTEM: All bar values in your output must be LOCAL to each track's "
        "first downbeat (T1 bar 0 = T1's first_downbeat_s, T2 bar 0 = T2's first_downbeat_s). "
        "Do NOT use global mix bar numbers. The zone data bars above are already in track-local space.\n\n"
    )
    return (
        concept_block
        + "You are planning a 2-track transition.\n\n"
        f"{coord_note}"
        f"{summaries}\n\n"
        f"Required window (from Phase 1 analysis): "
        f"T1 exits bar {window['t1_exit_bar']}, "
        f"T2 enters bar {window['t2_enter_bar']}, "
        f"overlap = EXACTLY {window['window_bars']} bars "
        f"(set fade_in.duration_bars = fade_out.duration_bars = {window['window_bars']}), "
        f"style={window['style']}\n\n"
        f"{zone_hints}"
        f"{examples_block}"
        f"{t1_table}\n\n"
        f"{t2_table}\n\n"
        "Using the zone data above, output the mix script JSON now."
    )
```

Note: `vocal_warning` call is removed; `_compute_zone_hints` now handles it.

- [ ] **Step 5: Add loop placement rule to _PLAN_TASK_SUFFIX**

Append to the `_PLAN_TASK_SUFFIX` string, before the closing `"""`:

```
---

**3. Loop placement rule**
loop.start_bar MUST reference a bar annotated [LOOP_SAFE] in the zone table above.
Never place a loop on a bar annotated [LOOP_UNSAFE_VOX] or [LOOP_UNSAFE_HARM].
```

- [ ] **Step 6: Run all derived hints tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py -v
```
Expected: all PASS

- [ ] **Step 7: Run full test suite to check no regressions**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/ -v 2>&1 | tail -30
```
Expected: all PASS (except any test that explicitly imports `_vocal_warning` — check and update if needed)

- [ ] **Step 8: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/mix_director.py claude-dj/tests/test_derived_hints.py && git commit -m "feat(mix_director): rewrite _compute_zone_hints with vocal/loop/technique blocks; remove _vocal_warning; add loop placement rule"
```

---

## Task 8: mix_director.py — Phase 1 profile injection

**Files:**
- Modify: `claude-dj/mix_director.py`

- [ ] **Step 1: Write failing test**

Append to `claude-dj/tests/test_derived_hints.py`:

```python
# ── Phase 1 profile injection ────────────────────────────────────────────────

from mix_director import _format_profiles_section


def test_profiles_section_empty_when_no_profiles():
    result = _format_profiles_section(None, None)
    assert result == ""


def test_profiles_section_shows_t1_outro():
    from schema import LoopCandidate, MixingProfile, TransitionWindow
    p1 = MixingProfile(
        vocal_bars=[[16, 48]],
        loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason="clean")],
        transition_windows=[TransitionWindow(bar=96, quality=9, character="drums-only")],
        intro_type="melodic",
        outro_type="drums-only",
        dj_notes="Clean outro from bar 96.",
    )
    result = _format_profiles_section(p1, None)
    assert "T1 MIXING PROFILE" in result
    assert "outro: drums-only" in result
    assert "bar 96" in result


def test_profiles_section_shows_t2_intro():
    from schema import MixingProfile
    p2 = MixingProfile(
        vocal_bars=[],
        loop_candidates=[],
        transition_windows=[],
        intro_type="drums-only",
        outro_type="fade-silence",
        dj_notes="Drums-only intro.",
    )
    result = _format_profiles_section(None, p2)
    assert "T2 MIXING PROFILE" in result
    assert "intro: drums-only" in result
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py::test_profiles_section_empty_when_no_profiles -v 2>&1 | tail -10
```
Expected: `ImportError: cannot import name '_format_profiles_section'`

- [ ] **Step 3: Add _format_profiles_section() to mix_director.py**

Add after `_format_peek_rows()`:

```python
def _format_profiles_section(t1_profile, t2_profile) -> str:
    """Format mixing profile summaries for Phase 1 window selection prompt."""
    if t1_profile is None and t2_profile is None:
        return ""

    lines: list[str] = []

    if t1_profile is not None:
        vocal_str = (
            "bars " + ", ".join(f"{s}–{e}" for s, e in t1_profile.vocal_bars)
            if t1_profile.vocal_bars else "none"
        )
        best_exit = t1_profile.transition_windows[0] if t1_profile.transition_windows else None
        exit_str = (
            f"bar {best_exit.bar} (quality={best_exit.quality}, {best_exit.character})"
            if best_exit else "unknown"
        )
        notes_preview = t1_profile.dj_notes[:120] + "…" if len(t1_profile.dj_notes) > 120 else t1_profile.dj_notes
        lines += [
            "T1 MIXING PROFILE:",
            f"  intro: {t1_profile.intro_type} | outro: {t1_profile.outro_type}",
            f"  vocals: {vocal_str} — avoid overlapping these bars during transition",
            f"  best exit window: {exit_str}",
            f"  DJ notes: \"{notes_preview}\"",
        ]

    if t2_profile is not None:
        first_voc = min(t2_profile.vocal_bars[0]) if t2_profile.vocal_bars else None
        first_harm = None  # not available at profile level
        voc_str = f"first vocal bar {first_voc}" if first_voc is not None else "no vocals detected"
        lines += [
            "",
            "T2 MIXING PROFILE:",
            f"  intro: {t2_profile.intro_type} | outro: {t2_profile.outro_type}",
            f"  {voc_str}",
        ]
        if t2_profile.dj_notes and "[stems unavailable" not in t2_profile.dj_notes:
            notes_preview = t2_profile.dj_notes[:120] + "…" if len(t2_profile.dj_notes) > 120 else t2_profile.dj_notes
            lines.append(f"  DJ notes: \"{notes_preview}\"")

    return "\n".join(lines) + "\n\n"
```

- [ ] **Step 4: Update select_transition_window() to inject profiles**

In `select_transition_window()`, after the `peek_section` is built (after the `except` block that catches peek failures), add:

```python
    # Profile summary injection (Phase 0 data)
    profiles_section = _format_profiles_section(
        getattr(t1, "mixing_profile", None),
        getattr(t2, "mixing_profile", None),
    )
```

Then update the `prompt` assembly line (which currently is `prompt = _WINDOW_PROMPT_TEMPLATE.format(summaries=summaries, peek_section=peek_section)`) to:

```python
    prompt = _WINDOW_PROMPT_TEMPLATE.format(
        summaries=summaries,
        peek_section=peek_section,
        profiles_section=profiles_section,
    )
```

And update `_WINDOW_PROMPT_TEMPLATE` to include the `{profiles_section}` slot. Change:

```python
_WINDOW_PROMPT_TEMPLATE = """\
Given these two track summaries, choose the optimal transition window.

{summaries}
{peek_section}
Output a single JSON object:
```

to:

```python
_WINDOW_PROMPT_TEMPLATE = """\
Given these two track summaries, choose the optimal transition window.

{summaries}
{profiles_section}{peek_section}
Output a single JSON object:
```

- [ ] **Step 5: Run profile injection tests**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/test_derived_hints.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add claude-dj/mix_director.py claude-dj/tests/test_derived_hints.py && git commit -m "feat(mix_director): add _format_profiles_section; inject mixing profile summaries into Phase 1 prompt"
```

---

## Task 9: Integration verification

**Files:**
- Read-only check

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -m pytest tests/ -v 2>&1 | tail -40
```
Expected: all PASS. Note the count — if any fail, diagnose before moving on.

- [ ] **Step 2: Smoke test analyze_transition_zone() output schema**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "
from analyze import analyze_transition_zone, _assign_tags, _build_vocal_regions
# Verify tag helpers work
tags = _assign_tags(drums=0.70, harmonic=0.05, vocals=0.05)
print('LOOP_SAFE tags:', tags)
assert 'LOOP_SAFE' in tags
tags2 = _assign_tags(drums=0.70, harmonic=0.05, vocals=0.50)
assert 'VOCAL_ACTIVE' in tags2 and 'LOOP_UNSAFE_VOX' in tags2
print('Vocal tags:', tags2)
# Verify vocal regions
regions = _build_vocal_regions([0.0, 0.5, 0.5, 0.0, 0.5])
print('Vocal regions:', regions)
assert regions == [(1, 2), (4, 4)]
print('All helpers OK')
"
```
Expected: prints OK, no assertions

- [ ] **Step 3: Verify _dict_to_analysis() handles both old and new cache shapes**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "
import dataclasses, json
from schema import *
from analyze import _dict_to_analysis

key = KeyInfo(camelot='8B', standard='C major', mode='major', tonic='C')
stem = StemPresence(presence=0, rms_db=-80.0)
stems_dc = SectionStems(drums=stem, bass=stem, vocals=stem, other=stem)
section = Section(label='groove', start_bar=0, end_bar=16, start_s=0.0, end_s=30.0, energy=5, loudness_dbfs=-12.0, stems=stems_dc)
a = TrackAnalysis(id='T1', title='X', artist='Y', file='/t.mp3', duration_s=60.0, bpm=128.0, first_downbeat_s=0.0, key=key, energy_overall=5, loudness_dbfs=-12.0, bar_grid=BarGrid(n_bars=32, beats_per_bar=4), energy_curve_per_bar='5'*32, sections=[section], cue_points=[CuePoint(name='mix_in', bar=0, type='phrase_start')], stems=StemPaths(vocals='', drums='', bass='', other=''))

# Old cache (no mixing_profile)
d_old = dataclasses.asdict(a)
d_old.pop('mixing_profile', None)
r_old = _dict_to_analysis(d_old)
assert r_old.mixing_profile is None, 'Old cache: should be None'
print('Old cache deserialization: OK')

# New cache (with mixing_profile)
p = MixingProfile(vocal_bars=[[4,8]], loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason='clean')], transition_windows=[TransitionWindow(bar=80, quality=8, character='drums-only')], intro_type='drums-only', outro_type='fade-silence', dj_notes='Test.')
a2 = dataclasses.replace(a, mixing_profile=p)
d_new = dataclasses.asdict(a2)
r_new = _dict_to_analysis(d_new)
assert r_new.mixing_profile is not None
assert r_new.mixing_profile.intro_type == 'drums-only'
print('New cache deserialization: OK')
"
```
Expected: both print OK

- [ ] **Step 4: Verify zone table renders vocals + tags**

```bash
cd /Users/DantesFolder/Claude\ DJ/claude-dj && python -c "
from mix_director import _format_zone_table
rows = [
    {'bar': 80, 'drums': 0.71, 'harmonic': 0.04, 'rms': 0.42, 'brightness': 0.35, 'onsets': 2, 'vocals': 0.08, 'tags': ['LOOP_SAFE']},
    {'bar': 81, 'drums': 0.65, 'harmonic': 0.03, 'rms': 0.44, 'brightness': 0.35, 'onsets': 2, 'vocals': 0.61, 'tags': ['VOCAL_ACTIVE', 'LOOP_UNSAFE_VOX']},
]
print(_format_zone_table(rows, 'T1', 'exit zone'))
"
```
Expected output contains `vox=0.08  [LOOP_SAFE]` and `vox=0.61  [VOCAL_ACTIVE] [LOOP_UNSAFE_VOX]`

- [ ] **Step 5: Final commit**

```bash
cd /Users/DantesFolder/Claude\ DJ && git add -p  # review any unstaged changes
git status
```

If clean, done. If there are unstaged changes from integration fixes, stage and commit:

```bash
git add claude-dj/analyze.py claude-dj/mix_director.py
git commit -m "fix: integration cleanup from transition intelligence layer"
```
