# claude-dj/tests/test_dsp.py
import numpy as np
import pytest
from pydub import AudioSegment

from executor import (
    TARGET_DBFS,
    _apply_smooth_bass_swap,
    _apply_soft_limiter,
    apply_loudness_match,
    bars_to_ms,
)


def _mono(samples_int16: np.ndarray, rate: int = 44100) -> AudioSegment:
    return AudioSegment(
        samples_int16.tobytes(), frame_rate=rate, sample_width=2, channels=1,
    )


def _hot_audio(db_over: float = 6, ms: int = 500, rate: int = 44100) -> AudioSegment:
    """White noise driven db_over dB above 0 dBFS."""
    max_val = float(1 << 15)
    n = int(rate * ms / 1000)
    rng = np.random.default_rng(0)
    noise = (rng.random(n) * 2 - 1) * max_val * (10 ** (db_over / 20))
    return _mono(np.clip(noise, -max_val, max_val - 1).astype(np.int16), rate)


def test_soft_limiter_output_within_unit_range():
    audio   = _hot_audio(db_over=6)
    limited = _apply_soft_limiter(audio)
    max_val = float(1 << 15)
    samples = np.array(limited.get_array_of_samples(), dtype=np.float32) / max_val
    assert np.all(samples >= -1.0), f"min={samples.min():.4f}"
    assert np.all(samples <=  1.0), f"max={samples.max():.4f}"


def test_loudness_match_rms_within_half_db_of_target():
    rate    = 44100
    max_val = float(1 << 15)
    t       = np.linspace(0, 1.0, rate, dtype=np.float32)
    gain    = 10 ** (-8.0 / 20)      # -8 dBFS peak
    tone    = (np.sin(2 * np.pi * 440 * t) * max_val * gain).astype(np.int16)
    audio   = _mono(tone, rate)

    # Use the actual RMS-based dBFS (pydub contract) as source_dbfs
    source_dbfs = audio.dBFS
    matched = apply_loudness_match(audio, source_dbfs)
    samples = np.array(matched.get_array_of_samples(), dtype=np.float32) / max_val
    rms_db  = 20 * np.log10(np.sqrt(np.mean(samples ** 2)) + 1e-9)
    assert abs(rms_db - TARGET_DBFS) < 0.5, f"rms_db={rms_db:.2f}, target={TARGET_DBFS}"


def test_loudness_match_skips_when_within_threshold():
    rate    = 44100
    max_val = float(1 << 15)
    gain    = 10 ** (TARGET_DBFS / 20)
    tone    = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, rate)) * max_val * gain).astype(np.int16)
    audio   = _mono(tone, rate)

    result = apply_loudness_match(audio, TARGET_DBFS)
    # Within 0.5 dB threshold → returned unchanged
    assert result is audio


def test_smooth_bass_swap_no_large_discontinuity():
    """No sample-to-sample jump > 3× local RMS in a window around the swap point."""
    rate    = 44100
    max_val = float(1 << 15)
    rng     = np.random.default_rng(1)
    n       = rate * 4   # 4 seconds
    noise   = (rng.random(n) * 2 - 1) * max_val * 0.5
    audio   = _mono(noise.astype(np.int16), rate)

    ref_bpm = 128.0
    swap_ms = bars_to_ms(4, ref_bpm)
    result  = _apply_smooth_bass_swap(audio, swap_ms, ref_bpm)

    samples    = np.array(result.get_array_of_samples(), dtype=np.float32)
    swap_sample = int(swap_ms * rate / 1000)
    # Check 200 ms window centred on swap point
    w_start    = max(0, swap_sample - int(0.1 * rate))
    w_end      = min(len(samples), swap_sample + int(0.1 * rate))
    window     = samples[w_start:w_end]
    local_rms  = np.sqrt(np.mean(window ** 2))

    if local_rms > 0:
        diffs = np.abs(np.diff(window))
        assert np.all(diffs < local_rms * 3), \
            f"Max diff {diffs.max():.1f} exceeds 3× local RMS {local_rms:.1f}"
