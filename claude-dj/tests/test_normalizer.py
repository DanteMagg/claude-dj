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


def test_phrase_snap_5_becomes_16():
    # round(5/8)*8 = 8, but DURATION_PREFERRED_MIN=16 raises it to 16
    assert _snap_duration_to_phrase(5) == 16


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
