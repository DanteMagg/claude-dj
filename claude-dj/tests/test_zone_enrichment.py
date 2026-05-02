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
