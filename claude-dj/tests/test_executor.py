# claude-dj/tests/test_executor.py
import numpy as np
import pytest
from pydub import AudioSegment

from executor import _apply_gain_ramp, bars_to_ms, compute_cursors_at_ms, render_chunk
from schema import MixAction, MixScript, MixTrackRef


def _noise(ms=1000, rate=44100) -> AudioSegment:
    """Non-silent mono audio for testing gain ramps."""
    rng = np.random.default_rng(42)
    samples = (rng.integers(-10000, 10000, int(rate * ms / 1000), dtype=np.int16))
    return AudioSegment(samples.tobytes(), frame_rate=rate, sample_width=2, channels=1)


def _script(actions, n_tracks=1) -> MixScript:
    tracks = [
        MixTrackRef(id=f"T{i+1}", path=f"/t{i+1}.mp3", bpm=128.0, first_downbeat_s=0.0)
        for i in range(n_tracks)
    ]
    return MixScript(mix_title="test", reasoning="", tracks=tracks, actions=actions)


def test_equal_power_sum_to_unity():
    """sin²(frac) + cos²(frac) == 1 — fade_in² + fade_out² == source² at every sample."""
    audio = _noise(1000)
    ramp_ms = 1000
    fade_in  = _apply_gain_ramp(audio, 0, 0, ramp_ms, 0.0, 1.0)
    fade_out = _apply_gain_ramp(audio, 0, 0, ramp_ms, 1.0, 0.0)

    max_val = float(1 << (audio.sample_width * 8 - 1))
    src_n  = np.array(audio.get_array_of_samples(),    dtype=np.float32) / max_val
    in_n   = np.array(fade_in.get_array_of_samples(),  dtype=np.float32) / max_val
    out_n  = np.array(fade_out.get_array_of_samples(), dtype=np.float32) / max_val

    src_pow = src_n ** 2
    sum_pow = in_n  ** 2 + out_n ** 2
    nonzero = src_pow > 0.01  # skip int16-quantization-noisy near-zero samples
    ratio = sum_pow[nonzero] / src_pow[nonzero]
    assert np.allclose(ratio, 1.0, atol=0.01), f"max deviation: {np.max(np.abs(ratio - 1.0)):.4f}"


def test_render_chunk_returns_non_silent_audio():
    """render_chunk with a play action returns non-silent audio."""
    audio = _noise(8000)
    actions = [MixAction(type="play", track="T1", at_bar=0, from_bar=0)]
    script = _script(actions)
    loaded = {"T1": audio}
    chunk = render_chunk(script, loaded, {}, 128.0, 0, 1000)
    assert chunk.rms > 0


def test_compute_cursors_play_sets_active():
    ref_bpm = 128.0
    script  = _script([MixAction(type="play", track="T1", at_bar=0, from_bar=0)])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(4, ref_bpm))
    assert cursors["T1"].active is True


def test_compute_cursors_fade_in_sets_active():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="fade_in", track="T1", start_bar=0, from_bar=0, duration_bars=8),
    ])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(4, ref_bpm))
    assert cursors["T1"].active is True
    assert cursors["T1"].fade_in_start_ms == 0


def test_compute_cursors_bass_cut_after_bass_swap():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="play",      track="T1", at_bar=0, from_bar=0),
        MixAction(type="bass_swap", track="T1", at_bar=8),
    ])
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(10, ref_bpm))
    assert cursors["T1"].bass_cut is True


def test_compute_cursors_bass_restored_on_incoming():
    ref_bpm = 128.0
    script  = _script([
        MixAction(type="play",      track="T1", at_bar=0,  from_bar=0),
        MixAction(type="fade_in",   track="T2", start_bar=8, duration_bars=8, from_bar=0),
        MixAction(type="bass_swap", track="T1", at_bar=12, incoming_track="T2"),
    ], n_tracks=2)
    cursors = compute_cursors_at_ms(script, ref_bpm, bars_to_ms(14, ref_bpm))
    assert cursors["T1"].bass_cut is True
    assert cursors["T2"].bass_cut is False


# ── Loop mechanics ─────────────────────────────────────────────────────────────

def test_loop_source_pos_during_loop():
    """cursor.source_pos_ms cycles within the phrase during a loop."""
    ref_bpm = 128.0
    bar_ms  = bars_to_ms(1, ref_bpm)
    script  = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=8, loop_bars=8, loop_repeats=2),
    ])
    # Halfway through the second repeat (bar 12 mix = bar 4 into phrase)
    t_ms    = bars_to_ms(20, ref_bpm)   # bar 8 + 4 into second repeat
    cursors = compute_cursors_at_ms(script, ref_bpm, t_ms)
    phrase_ms = bars_to_ms(8, ref_bpm)
    # Expected source pos: loop_source_offset (bar 8 ms) + (elapsed % phrase_ms)
    elapsed_in_loop = t_ms - bars_to_ms(8, ref_bpm)
    expected = bars_to_ms(8, ref_bpm) + (elapsed_in_loop % phrase_ms)
    assert cursors["T1"].source_pos_ms == expected


def test_loop_source_pos_after_loop_rebased():
    """After loop ends, source_pos_ms advances from post-loop offset, not from track start."""
    ref_bpm  = 128.0
    # Loop bar 8 for 8 bars × 2 repeats → loop ends at mix bar 24 (8 + 8*2).
    # Post-loop, source should be at bar 8+8*2=24, advancing from there.
    script   = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=8, loop_bars=8, loop_repeats=2),
    ])
    loop_end_ms  = bars_to_ms(24, ref_bpm)
    extra_ms     = bars_to_ms(4, ref_bpm)   # 4 bars after loop ends
    cursors      = compute_cursors_at_ms(script, ref_bpm, loop_end_ms + extra_ms)
    # Source should be at bar 24 (loop_source_offset + phrase * repeats) + 4 bars
    expected_src = bars_to_ms(24, ref_bpm) + extra_ms
    assert cursors["T1"].source_pos_ms == expected_src, (
        f"Expected source at bar 28 ({expected_src}ms), "
        f"got {cursors['T1'].source_pos_ms}ms"
    )


def test_loop_post_loop_not_jumped_ahead():
    """Regression: before the cursor fix, post-loop source was phrase_ms*(repeats-1) ahead."""
    ref_bpm  = 128.0
    # Without the fix: source_pos = play_from_ms + elapsed = 0 + 28_bars = 28_bars.
    # Wrong: it should be at bar 24 + 4 = 28 anyway in this specific case.
    # Use a case where the bug is visible: play from bar 4 (from_bar=4), loop bar 12 for
    # 8 bars × 2. Post-loop at mix bar 28+4=32: source should be at bar 4+8+8+4=24,
    # but without fix it'd be bar 4 + 32 = 36 (4 bars too far).
    script   = _script([
        MixAction(type="play", track="T1", at_bar=0, from_bar=4),
        MixAction(type="loop", track="T1", start_bar=8, loop_bars=8, loop_repeats=2),
    ])
    loop_end_ms = bars_to_ms(24, ref_bpm)   # bar 8 + 8*2 = 24
    extra_ms    = bars_to_ms(4, ref_bpm)
    cursors     = compute_cursors_at_ms(script, ref_bpm, loop_end_ms + extra_ms)
    # loop_source_offset = from_bar=4 + (loop_start=8 - at=0) = bar 12
    # post-loop source = bar 12 + 8*2 = 28; +4 extra = bar 32
    expected_src = bars_to_ms(32, ref_bpm)
    assert cursors["T1"].source_pos_ms == expected_src


def test_normalizer_snaps_loop_start_bar():
    """_clamp_loops should snap start_bar to phrase multiple."""
    from normalizer import _clamp_loops
    actions = [MixAction(type="loop", track="T1", start_bar=83, loop_bars=8, loop_repeats=1)]
    result  = _clamp_loops(actions)
    assert result[0].start_bar == 80   # floored to nearest 8-bar boundary


def test_normalizer_snaps_loop_bars():
    """_clamp_loops snaps loop_bars to phrase multiples."""
    from normalizer import _clamp_loops
    actions = [MixAction(type="loop", track="T1", start_bar=16, loop_bars=6, loop_repeats=1)]
    result  = _clamp_loops(actions)
    assert result[0].loop_bars == 8   # 6 rounds to nearest 8


def test_render_chunk_loops_audible():
    """Rendering a loop action produces non-silent audio for the repeated window."""
    ref_bpm = 128.0
    audio   = _noise(ms=60_000)  # 60s of noise — well beyond 8 bars
    actions = [
        MixAction(type="play", track="T1", at_bar=0, from_bar=0),
        MixAction(type="loop", track="T1", start_bar=8, loop_bars=8, loop_repeats=2),
    ]
    script = _script(actions)
    loaded = {"T1": audio}
    # Render a chunk inside the second repeat of the loop
    chunk_start = bars_to_ms(18, ref_bpm)
    chunk       = render_chunk(script, loaded, {}, ref_bpm, chunk_start, 1000)
    assert chunk.rms > 0, "Loop second repeat produced silence"
