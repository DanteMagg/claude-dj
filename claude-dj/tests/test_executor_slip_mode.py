"""
Verify that loop actions use slip-mode semantics: the track's source position
continues advancing past the loop boundary during the loop. When the loop ends,
source_pos resumes from where the track would have been without the loop.
"""
import pytest
from executor import bars_to_ms, compute_cursors_at_ms
from schema import MixAction, MixScript, MixTrackRef


def _script(actions, n_tracks=1):
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=120.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


def test_loop_source_pos_stays_in_phrase_during_loop():
    """While loop is active, source_pos cycles within the loop phrase."""
    bpm = 120.0
    loop_start_bar = 8
    loop_bars = 2
    phrase_ms = bars_to_ms(loop_bars, bpm)
    loop_start_ms = bars_to_ms(loop_start_bar, bpm)
    # Mid-way through second repeat (1.5 * phrase_ms into the loop window)
    target_ms = loop_start_ms + int(phrase_ms * 1.5)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=loop_start_bar,
                  loop_bars=loop_bars, loop_repeats=4),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    # 1.5 phrases elapsed → 0.5 phrases into current repeat
    expected_source = loop_start_ms + int(phrase_ms * 0.5)
    assert abs(c.source_pos_ms - expected_source) <= 10


def test_loop_source_pos_after_loop_ends_is_slip_position():
    """After loop completes, source_pos == where the track would be without the loop."""
    bpm = 120.0
    loop_start_bar = 8
    loop_bars = 2
    loop_repeats = 3
    phrase_ms = bars_to_ms(loop_bars, bpm)
    loop_start_ms = bars_to_ms(loop_start_bar, bpm)
    loop_end_ms = loop_start_ms + phrase_ms * loop_repeats
    # Half a bar after loop ends
    target_ms = loop_end_ms + bars_to_ms(1, bpm) // 2

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=loop_start_bar,
                  loop_bars=loop_bars, loop_repeats=loop_repeats),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    # Slip position == play_from_ms + (target_ms - original_mix_start_ms) = 0 + target_ms
    assert abs(c.source_pos_ms - target_ms) <= 10


def test_loop_end_rebases_mix_start():
    """After loop ends, mix_start_ms is set to loop_end_ms."""
    bpm = 120.0
    loop_start_ms = bars_to_ms(4, bpm)
    phrase_ms = bars_to_ms(2, bpm)
    loop_end_ms = loop_start_ms + phrase_ms * 2
    target_ms = loop_end_ms + bars_to_ms(1, bpm)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=4, loop_bars=2, loop_repeats=2),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    assert c.loop_start_ms is None        # loop is done
    assert c.mix_start_ms == loop_end_ms


def test_one_bar_loop_cycles_correctly():
    """1-bar loops cycle source_pos within a single bar."""
    bpm = 120.0
    loop_start_ms = bars_to_ms(16, bpm)
    phrase_ms = bars_to_ms(1, bpm)
    # 2.7 phrases into the loop window
    target_ms = loop_start_ms + int(phrase_ms * 2.7)

    script = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=16, loop_bars=1, loop_repeats=8),
    ])
    cursors = compute_cursors_at_ms(script, bpm, target_ms)
    c = cursors["T1"]
    # 2.7 phrases → 0.7 phrases into current repeat
    expected_source = loop_start_ms + int(phrase_ms * 0.7)
    assert abs(c.source_pos_ms - expected_source) <= 10
