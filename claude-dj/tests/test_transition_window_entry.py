# claude-dj/tests/test_transition_window_entry.py
"""
Regression cover for the mid-set exit bar bug.

select_transition_window picks t1_exit_bar from T1's whole timeline. Every track after
the first is mixed in part-way through, so bars before its entry point never play. Left
unclamped the planner returns exit bars that sit behind the playhead — measured on the
four_tracks set as t1_exit_bar 80 / 0 / 16 for decks that had entered at source bars
0 / 24 / 16, which put transition 3 ahead of transition 2 once merged.
"""
import dataclasses

from dj_session import merge_transition
from mix_director import MIN_PLAY_BARS, clamp_t1_exit_bar
from schema import MixAction, MixScript, MixTrackRef


# ── clamp_t1_exit_bar ─────────────────────────────────────────────────────────

def test_entry_at_zero_keeps_old_behaviour():
    # Opening track: no floor to apply beyond the phrase snap.
    assert clamp_t1_exit_bar(83, n_bars=200, window_bars=16, entered_at_bar=0) == 80


def test_ceiling_still_leaves_room_for_the_overlap():
    # 200 - 32 = 168, already phrase-aligned.
    assert clamp_t1_exit_bar(190, n_bars=200, window_bars=32, entered_at_bar=0) == 168


def test_exit_before_entry_is_pushed_past_it():
    # The measured T2→T3 case: deck entered at source bar 24, planner returned 0.
    assert clamp_t1_exit_bar(0, n_bars=200, window_bars=16, entered_at_bar=24) == 56


def test_exit_shortly_after_entry_is_pushed_to_min_play():
    # The measured T3→T4 case: entered at 16, planner returned 16 — a 0-bar run.
    assert clamp_t1_exit_bar(16, n_bars=200, window_bars=16, entered_at_bar=16) == 48


def test_floor_is_phrase_aligned_upward():
    # 20 + 32 = 52 is not a phrase multiple; rounding down would break the floor.
    assert clamp_t1_exit_bar(0, n_bars=200, window_bars=16, entered_at_bar=20) == 56


def test_valid_exit_is_left_alone():
    assert clamp_t1_exit_bar(128, n_bars=200, window_bars=16, entered_at_bar=24) == 128


def test_ceiling_wins_when_min_play_does_not_fit():
    # Entered at 80 of a 100-bar track: 80 + 32 overruns the audio, so the latest legal
    # exit is the answer rather than an exit bar with no track left under it.
    result = clamp_t1_exit_bar(0, n_bars=100, window_bars=16, entered_at_bar=80)
    assert result == 80
    assert result + 16 <= 100


def test_track_shorter_than_the_overlap_clamps_to_zero():
    assert clamp_t1_exit_bar(40, n_bars=8, window_bars=16, entered_at_bar=0) == 0


def test_result_never_precedes_entry_across_a_sweep():
    n_bars = 256
    for entered in range(0, 200, 4):
        exit_bar = clamp_t1_exit_bar(0, n_bars, window_bars=16, entered_at_bar=entered)
        assert 0 <= exit_bar <= n_bars - 16
        # Either the track gets its full minimum run, or it was cut short only because
        # the ceiling had no room left.
        assert exit_bar >= entered + MIN_PLAY_BARS or exit_bar == ((n_bars - 16) // 8) * 8


# ── merge_transition offsets ──────────────────────────────────────────────────

def _sub_script() -> MixScript:
    """A 2-track transition in track-local bars, as Claude writes it."""
    return MixScript(
        mix_title="sub",
        reasoning="",
        tracks=[
            MixTrackRef(id="T1", path="/a.mp3", bpm=128.0, first_downbeat_s=0.0),
            MixTrackRef(id="T2", path="/b.mp3", bpm=128.0, first_downbeat_s=0.0),
        ],
        actions=[
            MixAction(type="play",     track="T1", at_bar=0,  from_bar=0),
            MixAction(type="fade_out", track="T1", start_bar=80, duration_bars=16),
            MixAction(type="fade_in",  track="T2", start_bar=80, duration_bars=16, from_bar=0),
            MixAction(type="play",     track="T2", at_bar=96, from_bar=16),
        ],
    )


def _global_script() -> MixScript:
    return MixScript(
        mix_title="global",
        reasoning="",
        tracks=[MixTrackRef(id="deck_a", path="/a.mp3", bpm=128.0, first_downbeat_s=0.0)],
        actions=[MixAction(type="play", track="deck_a", at_bar=100, from_bar=24)],
    )


def test_t1_offset_accounts_for_the_entry_bar():
    # deck_a started at global bar 100 playing from its own bar 24, so its local bar 80
    # is audible at global 100 + (80 - 24) = 156.
    current_start, current_from = 100, 24
    merged, _ = merge_transition(
        _global_script(), _sub_script(), "deck_a", "deck_b",
        t2_offset=300,
        t1_offset=current_start - current_from,
    )
    fade_out = next(a for a in merged.actions if a.type == "fade_out" and a.track == "deck_a")
    assert fade_out.start_bar == 156


def test_t2_keeps_its_own_offset():
    merged, next_start = merge_transition(
        _global_script(), _sub_script(), "deck_a", "deck_b",
        t2_offset=300,
        t1_offset=100 - 24,
    )
    fade_in = next(a for a in merged.actions if a.type == "fade_in" and a.track == "deck_b")
    play_b  = next(a for a in merged.actions if a.type == "play" and a.track == "deck_b")
    assert fade_in.start_bar == 380
    assert play_b.at_bar == 396
    assert next_start == 396
    # from_bar is a source offset, not a timeline bar — merging must not shift it.
    assert play_b.from_bar == 16


def test_redundant_t1_play_at_bar_zero_is_dropped():
    merged, _ = merge_transition(
        _global_script(), _sub_script(), "deck_a", "deck_b",
        t2_offset=300,
        t1_offset=76,
    )
    plays_a = [a for a in merged.actions if a.type == "play" and a.track == "deck_a"]
    assert len(plays_a) == 1          # only the one already in the global script
    assert plays_a[0].at_bar == 100


def test_clamped_exit_keeps_transitions_in_order():
    """
    End-to-end shape of the reported failure: three consecutive transitions whose decks
    enter at source bars 0 / 24 / 16. With the clamp applied, each merged transition
    lands strictly after the one before it.
    """
    entries = [0, 24, 16]
    raw_exits = [80, 0, 16]           # what the planner returned unclamped
    n_bars = 200

    current_start, current_from = 0, 0
    previous_bar = -1
    for entered, raw in zip(entries, raw_exits):
        current_from = entered
        exit_bar = clamp_t1_exit_bar(raw, n_bars, window_bars=16, entered_at_bar=current_from)
        global_exit = exit_bar + (current_start - current_from)
        assert global_exit > previous_bar
        previous_bar = global_exit
        # Next deck takes over where this transition's fade completes.
        current_start = global_exit + 16
