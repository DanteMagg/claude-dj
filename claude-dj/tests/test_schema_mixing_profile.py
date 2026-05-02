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
    assert d["vocal_bars"] == [(4, 8)]  # plain tuples stay as tuples in Python 3.12 asdict
    assert d["loop_candidates"][0]["bars"] == 8
