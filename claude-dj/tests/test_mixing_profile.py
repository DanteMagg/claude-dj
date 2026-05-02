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


def test_no_stems_returns_profile_with_empty_vocals():
    """build_mixing_profile with no_stems=True: vocal_bars empty, dj_notes contains stems note."""
    from unittest.mock import patch
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
