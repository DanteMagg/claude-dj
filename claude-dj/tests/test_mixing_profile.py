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
