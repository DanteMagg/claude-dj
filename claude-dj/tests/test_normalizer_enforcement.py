import pytest
from normalizer import normalize
from schema import MixAction, MixScript, MixTrackRef


def _script(actions, n_tracks=2):
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=128.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


# ── T2 bass=0 enforcement ──────────────────────────────────────────────────


def test_t2_fade_in_bass_forced_to_zero():
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16,
                  stems={"drums": 0.8, "bass": 0.9, "other": 0.6}),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems["bass"] == 0.0


def test_t2_fade_in_bass_zero_already_unchanged():
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16,
                  stems={"drums": 0.8, "bass": 0.0, "other": 0.6}),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems["bass"] == 0.0


def test_t2_fade_in_no_stems_unaffected():
    s = _script([
        MixAction(type="fade_in",  track="T2", start_bar=16, duration_bars=16),
        MixAction(type="fade_out", track="T1", start_bar=16, duration_bars=16),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.stems is None


# ── EQ duration injection ──────────────────────────────────────────────────


def test_eq_duration_injected_when_missing():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
        MixAction(type="eq",       track="T1", bar=16,    low=0.0),
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16),
    ])
    result = normalize(s)
    eq_a = next(a for a in result.actions if a.type == "eq" and a.track == "T1" and a.bar == 16)
    assert eq_a.eq_duration_bars == 4


def test_eq_duration_not_overwritten_when_present():
    s = _script([
        MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
        MixAction(type="eq",       track="T1", bar=16,    low=0.0, eq_duration_bars=2),
        MixAction(type="fade_out", track="T1", start_bar=32, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=32, duration_bars=16),
    ])
    result = normalize(s)
    eq_a = next(a for a in result.actions if a.type == "eq" and a.track == "T1" and a.bar == 16)
    assert eq_a.eq_duration_bars == 2


# ── 1-bar loop support ─────────────────────────────────────────────────────


def test_one_bar_loop_preserved():
    s = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=80, loop_bars=1, loop_repeats=4),
        MixAction(type="fade_out", track="T1", start_bar=88, duration_bars=16),
        MixAction(type="fade_in",  track="T2", start_bar=88, duration_bars=16),
    ])
    result = normalize(s)
    loop_a = next(a for a in result.actions if a.type == "loop")
    assert loop_a.loop_bars == 1


# ── Anchor-first ×8 phrase snapping ───────────────────────────────────────


def test_fade_in_snapped_to_phrase_boundary():
    s = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_out",  track="T1", start_bar=20, duration_bars=16),
        MixAction(type="fade_in",   track="T2", start_bar=20, duration_bars=16),
        MixAction(type="bass_swap", track="T1", at_bar=28, incoming_track="T2"),
    ])
    result = normalize(s)
    fi = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert fi.start_bar % 8 == 0


def test_bass_swap_offset_preserved_after_anchor_snap():
    # fade_in at bar 20 → snaps to 16 (delta=-4)
    # bass_swap was 8 bars after fade_in (bar 28) → should be 8 bars after snapped (bar 24)
    s = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_out",  track="T1", start_bar=20, duration_bars=16),
        MixAction(type="fade_in",   track="T2", start_bar=20, duration_bars=16),
        MixAction(type="bass_swap", track="T1", at_bar=28, incoming_track="T2"),
    ])
    result = normalize(s)
    swap = next(a for a in result.actions if a.type == "bass_swap")
    fi   = next(a for a in result.actions if a.type == "fade_in" and a.track == "T2")
    assert swap.at_bar > fi.start_bar
