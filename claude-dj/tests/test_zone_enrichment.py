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
