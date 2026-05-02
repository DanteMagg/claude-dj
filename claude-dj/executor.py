from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from pydub import AudioSegment
from pydub.effects import high_pass_filter, low_pass_filter
from scipy.signal import butter, sosfilt

from schema import MixAction, MixScript, MixTrackRef


@dataclass
class TrackCursor:
    """Playback state of one track at a specific point in mix time."""
    active: bool = False
    source_pos_ms: int = 0          # position in loaded[tid] at the queried mix_ms
    mix_start_ms: int = 0           # mix ms when this play/fade_in started
    play_from_ms: int = 0           # source offset at mix_start_ms
    fade_in_start_ms: Optional[int] = None
    fade_in_end_ms: Optional[int] = None
    fade_out_start_ms: Optional[int] = None
    fade_out_end_ms: Optional[int] = None
    bass_cut: bool = False          # True after bass_swap
    eq: tuple[float, float, float] = field(default_factory=lambda: (1.0, 1.0, 1.0))
    loop_start_ms: Optional[int] = None
    loop_phrase_ms: Optional[int] = None
    loop_end_ms: Optional[int] = None
    loop_source_offset: int = 0     # source pos at loop_start_ms
    fade_in_stems: Optional[dict[str, float]] = None  # stem volumes during active fade_in
    eq_start_ms: Optional[int] = None  # mix-time ms when the eq action started
    eq_end_ms: Optional[int] = None    # mix-time ms when the eq action expires


def bars_to_ms(bars: float, bpm: float) -> int:
    return int(bars * 4 * 60_000 / bpm)


def load_track(path: str) -> AudioSegment:
    p = Path(path)
    fmt = p.suffix.lstrip(".").lower()
    if fmt == "mp3":
        return AudioSegment.from_mp3(path)
    if fmt == "flac":
        return AudioSegment.from_file(path, format="flac")
    return AudioSegment.from_wav(path)


def time_stretch(audio: AudioSegment, src_bpm: float, dst_bpm: float) -> AudioSegment:
    if abs(src_bpm - dst_bpm) < 0.5:
        return audio
    ratio = dst_bpm / src_bpm
    try:
        import pyrubberband as pyrb
        max_val = float(1 << (audio.sample_width * 8 - 1))
        samples = np.array(audio.get_array_of_samples()).astype(np.float32) / max_val
        if audio.channels == 2:
            samples = samples.reshape(-1, 2).T
        stretched = pyrb.time_stretch(samples, audio.frame_rate, ratio)
        if audio.channels == 2:
            out = np.clip(stretched.T.flatten() * max_val, -max_val, max_val - 1).astype(np.int16)
        else:
            out = np.clip(stretched * max_val, -max_val, max_val - 1).astype(np.int16)
        return audio._spawn(out.tobytes())
    except Exception:
        new_frame_rate = int(audio.frame_rate * ratio)
        return audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate}).set_frame_rate(audio.frame_rate)


def _shelf_filter(
    samples: np.ndarray, sr: int, cutoff: int, gain_db: float, shelf: str,
) -> np.ndarray:
    """
    Partial-blend shelving filter. shelf='low' | 'high'.
    gain_db negative = cut, positive = boost. Full effect at ±12 dB.
    """
    sos      = butter(1, cutoff / (sr / 2), btype=shelf, output="sos")
    filtered = sosfilt(sos, samples)
    blend    = abs(gain_db) / 12.0
    return samples + (filtered - samples) * blend


def _hpf_cutoff_hz(low: float) -> float:
    """
    Map the EQ `low` parameter (0–1) to a HPF cutoff frequency.
      low=0.0  →  200 Hz  (maximum bass cut — kick/sub mostly removed)
      low=0.5  →   80 Hz  (sub-bass only cut, kicks intact)
      low=1.0  →    0 Hz  (bypass — no filter applied)
    Uses a power curve calibrated so low=0.5 ≈ 80 Hz.
    """
    if low >= 1.0:
        return 0.0
    # Power exponent: solve 200 * (1-0.5)^k = 80 → k = log(0.4)/log(0.5) ≈ 1.32
    return 200.0 * ((1.0 - low) ** 1.32)


def apply_eq(audio: "AudioSegment", low: float, mid: float, high: float) -> "AudioSegment":
    """
    3-band EQ.
      low:  0–1 controls a variable-frequency Butterworth HPF.
            low=0 → HPF at 200 Hz, low=0.5 → HPF at ~80 Hz, low=1 → bypass.
      high: 0–1 controls a 8 kHz high shelving filter (0 → -12 dB, 1 → unity).
      mid:  0–1 maps to a ±6 dB broadband gain trim.
    """
    low  = max(0.0, min(low,  1.0))
    mid  = max(0.0, min(mid,  1.0))
    high = max(0.0, min(high, 1.0))

    sr      = audio.frame_rate
    max_val = float(1 << (audio.sample_width * 8 - 1))
    raw     = np.array(audio.get_array_of_samples(), dtype=np.float32) / max_val

    if audio.channels == 2:
        samples = raw.reshape(-1, 2)
    else:
        samples = raw.reshape(-1, 1)

    result = samples.copy()

    # Low band: variable-frequency HPF (continuous cutoff, not a shelf)
    if low < 1.0:
        cutoff = _hpf_cutoff_hz(low)
        if cutoff > 10.0:
            nyq = sr / 2.0
            sos = butter(2, cutoff / nyq, btype="high", output="sos")
            for ch in range(audio.channels):
                result[:, ch] = sosfilt(sos, result[:, ch])

    # High band: shelving filter (unchanged behaviour)
    if high != 1.0:
        high_gain_db = 12.0 * (high - 1.0)
        for ch in range(audio.channels):
            result[:, ch] = _shelf_filter(result[:, ch], sr, 8000, high_gain_db, "low")

    # Mid band: broadband gain trim
    if mid != 1.0:
        gain_db = max(-6.0, min(6.0, 12.0 * (mid - 0.5)))
        result *= 10 ** (gain_db / 20)

    out = np.clip(result.flatten() * max_val, -max_val, max_val - 1).astype(np.int16)
    return audio._spawn(out.tobytes())


TARGET_DBFS = -14.0


def apply_loudness_match(seg: "AudioSegment", source_dbfs: float) -> "AudioSegment":
    gain_db = TARGET_DBFS - source_dbfs
    if abs(gain_db) > 0.5:
        return seg.apply_gain(gain_db)
    return seg


def _stem_dir_for_track(track_id: str, script: MixScript) -> Path:
    for t in script.tracks:
        if t.id == track_id:
            from analyze import file_hash
            h = file_hash(t.path)
            return Path(__file__).parent / "cache" / h / "stems"
    return Path("/nonexistent")


def _apply_gain_ramp(
    audio: AudioSegment,
    chunk_start_ms: float,
    ramp_start_ms: float,
    ramp_end_ms: float,
    gain_at_ramp_start: float,
    gain_at_ramp_end: float,
) -> AudioSegment:
    """
    Apply a time-accurate gain ramp over [ramp_start_ms, ramp_end_ms].
    Outside that window the gain is clamped to the nearer endpoint value.
    chunk_start_ms is the mix-time position of sample 0 in `audio`.
    """
    max_val = float(1 << (audio.sample_width * 8 - 1))
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    n_frames = len(samples) // audio.channels

    chunk_end_ms = chunk_start_ms + len(audio)
    t = np.linspace(chunk_start_ms, chunk_end_ms, n_frames, endpoint=False)

    ramp_dur = ramp_end_ms - ramp_start_ms
    if ramp_dur <= 0:
        gain = np.full(n_frames, gain_at_ramp_start, dtype=np.float32)
    else:
        frac = np.clip((t - ramp_start_ms) / ramp_dur, 0.0, 1.0)
        # Perceptually smooth curve from gain_at_ramp_start → gain_at_ramp_end.
        # Uses sin² (equal-power) interpolation which works correctly for any
        # start/end gain pair — not just (0→1) or (1→0).
        if gain_at_ramp_end >= gain_at_ramp_start:
            curve = np.sin(frac * np.pi / 2).astype(np.float32)  # 0 → 1
        else:
            curve = np.cos(frac * np.pi / 2).astype(np.float32)  # 1 → 0
        gain = gain_at_ramp_start + (gain_at_ramp_end - gain_at_ramp_start) * curve

    if audio.channels == 2:
        gain = np.repeat(gain, 2)
    out = np.clip(samples * gain[: len(samples)], -max_val, max_val - 1).astype(np.int16)
    return audio._spawn(out.tobytes())


def _apply_smooth_bass_swap(
    layer: AudioSegment,
    swap_ms: int,
    ref_bpm: float,
) -> AudioSegment:
    """
    Crossfade from original signal to HPF-filtered signal over 2 bars,
    then continue with full HPF after the ramp. Avoids the click from an
    instant high-pass cut.
    """
    if swap_ms >= len(layer):
        return layer
    ramp_ms  = bars_to_ms(2, ref_bpm)
    ramp_end = min(swap_ms + ramp_ms, len(layer))
    region   = layer[swap_ms:ramp_end]
    actual_ms = len(region)

    original_fade = _apply_gain_ramp(region, 0, 0, actual_ms, 1.0, 0.0)
    filtered_fade = _apply_gain_ramp(high_pass_filter(region, 200), 0, 0, actual_ms, 0.0, 1.0)
    blended = original_fade.overlay(filtered_fade)

    result = layer[:swap_ms] + blended
    if ramp_end < len(layer):
        result = result + high_pass_filter(layer[ramp_end:], 200)
    return result


EQ_XFADE_MS = 150  # linear crossfade at each EQ chunk boundary


def _linear_xfade(a: "AudioSegment", b: "AudioSegment", fade_ms: int) -> "AudioSegment":
    """
    Returns a segment of length `fade_ms` that linearly crosses from `a` to `b`.
    Both inputs must be at least `fade_ms` long; only the first `fade_ms` of each is used.
    """
    max_val = float(1 << (a.sample_width * 8 - 1))
    sa = np.array(a[:fade_ms].get_array_of_samples(), dtype=np.float32) / max_val
    sb = np.array(b[:fade_ms].get_array_of_samples(), dtype=np.float32) / max_val
    n = len(sa) // a.channels
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if a.channels == 2:
        ramp = np.repeat(ramp, 2)
    ramp = ramp[: len(sa)]
    mixed = sa * (1.0 - ramp) + sb * ramp
    out = np.clip(mixed * max_val, -max_val, max_val - 1).astype(np.int16)
    return a._spawn(out.tobytes())


def _apply_soft_limiter(canvas: "AudioSegment") -> "AudioSegment":
    """
    Tanh-based soft clipper at -1 dBFS ceiling. Prevents clipping when two
    tracks overlap at full gain during a crossfade.
    """
    samples = np.array(canvas.get_array_of_samples(), dtype=np.float32)
    max_val = float(1 << (canvas.sample_width * 8 - 1))
    normalized = samples / max_val
    ceiling = 0.891  # -1 dBFS ≈ 10^(-1/20)
    limited = np.tanh(normalized * ceiling) * ceiling
    out = np.clip(limited * max_val, -max_val, max_val - 1).astype(np.int16)
    return canvas._spawn(out.tobytes())


def compute_cursors_at_ms(
    script: MixScript,
    ref_bpm: float,
    target_ms: int,
) -> dict[str, TrackCursor]:
    """
    Replay all MixActions up to target_ms using pure bar arithmetic (no audio I/O).
    Returns the playback state of every track at that moment.
    """
    cursors: dict[str, TrackCursor] = {t.id: TrackCursor() for t in script.tracks}

    def sort_key(a: MixAction) -> int:
        candidates = [a.at_bar, a.start_bar, a.bar]
        return min((b for b in candidates if b is not None), default=0)

    for action in sorted(script.actions, key=sort_key):
        tid = action.track
        c = cursors[tid]

        if action.type == "play":
            at_ms   = bars_to_ms(action.at_bar or 0,   ref_bpm)
            from_ms = bars_to_ms(action.from_bar or 0, ref_bpm)
            if at_ms <= target_ms:
                c.active            = True
                c.mix_start_ms      = at_ms
                c.play_from_ms      = from_ms
                c.fade_in_start_ms  = None
                c.fade_in_end_ms    = None
                c.fade_out_start_ms = None
                c.fade_out_end_ms   = None
                c.loop_start_ms     = None

        elif action.type == "fade_in":
            at_ms   = bars_to_ms(action.start_bar or 0,      ref_bpm)
            from_ms = bars_to_ms(action.from_bar or 0,       ref_bpm)
            dur_ms  = bars_to_ms(action.duration_bars or 8,  ref_bpm)
            if at_ms <= target_ms:
                c.active           = True
                c.mix_start_ms     = at_ms
                c.play_from_ms     = from_ms
                c.fade_in_start_ms = at_ms
                c.fade_in_end_ms   = at_ms + dur_ms
                c.fade_in_stems    = action.stems

        elif action.type == "fade_out":
            start_ms = bars_to_ms(action.start_bar or 0,     ref_bpm)
            dur_ms   = bars_to_ms(action.duration_bars or 8, ref_bpm)
            if start_ms <= target_ms:
                c.fade_out_start_ms = start_ms
                c.fade_out_end_ms   = start_ms + dur_ms
                if target_ms >= start_ms + dur_ms:
                    c.active = False

        elif action.type == "bass_swap":
            swap_ms = bars_to_ms(action.at_bar or 0, ref_bpm)
            if swap_ms <= target_ms:
                c.bass_cut = True
                if action.incoming_track:
                    inc = cursors.get(action.incoming_track)
                    if inc:
                        inc.bass_cut = False  # bass restored on incoming

        elif action.type == "eq":
            # Persistent: eq holds from bar onward (no end limit).
            bar_ms = bars_to_ms(action.bar or 0, ref_bpm)
            if target_ms >= bar_ms:
                c.eq = (
                    action.low  if action.low  is not None else 1.0,
                    action.mid  if action.mid  is not None else 1.0,
                    action.high if action.high is not None else 1.0,
                )
                c.eq_start_ms = bar_ms
                c.eq_end_ms   = None  # sustained indefinitely

        elif action.type == "loop":
            loop_start_ms  = bars_to_ms(action.start_bar or 0,    ref_bpm)
            loop_phrase_ms = bars_to_ms(action.loop_bars or 8,    ref_bpm)
            loop_repeats   = action.loop_repeats or 1
            loop_end_ms    = loop_start_ms + loop_phrase_ms * loop_repeats
            if loop_start_ms <= target_ms < loop_end_ms:
                c.loop_start_ms     = loop_start_ms
                c.loop_phrase_ms    = loop_phrase_ms
                c.loop_end_ms       = loop_end_ms
                c.loop_source_offset = c.play_from_ms + (loop_start_ms - c.mix_start_ms)
            elif target_ms >= loop_end_ms:
                # Rebase cursor so source_pos_ms is correct after the loop ends.
                # Without this, the linear formula (play_from_ms + elapsed) treats mix time
                # as if the loop never ran, landing the renderer phrase_ms*(repeats-1) ahead.
                loop_source_offset = c.play_from_ms + (loop_start_ms - c.mix_start_ms)
                c.play_from_ms = loop_source_offset + loop_phrase_ms * loop_repeats
                c.mix_start_ms = loop_end_ms
                c.loop_start_ms = None  # loop completed

    # Compute source_pos_ms for every active track
    for c in cursors.values():
        if not c.active:
            c.source_pos_ms = 0
            continue
        if c.loop_start_ms is not None and c.loop_phrase_ms:
            elapsed_in_loop = target_ms - c.loop_start_ms
            pos_in_phrase   = elapsed_in_loop % c.loop_phrase_ms
            c.source_pos_ms = max(0, c.loop_source_offset + pos_in_phrase)
        else:
            c.source_pos_ms = max(0, c.play_from_ms + (target_ms - c.mix_start_ms))

    return cursors


def render_chunk(
    script: MixScript,
    loaded: dict[str, AudioSegment],
    stem_layers: dict[tuple[str, str], AudioSegment],
    ref_bpm: float,
    start_ms: int,
    chunk_ms: int,
) -> AudioSegment:
    """
    Render a time window [start_ms, start_ms+chunk_ms) of the mix without building
    the full timeline. Suitable for real-time streaming playback.

    Fade-in stem volumes are approximated as a single gain ramp (full per-stem mixing
    is only available via the offline render() path).
    """
    if not loaded:
        return AudioSegment.silent(duration=chunk_ms)

    target_rate = next(iter(loaded.values())).frame_rate
    end_ms      = start_ms + chunk_ms
    cursors     = compute_cursors_at_ms(script, ref_bpm, start_ms)
    canvas      = AudioSegment.silent(duration=chunk_ms, frame_rate=target_rate)

    for tid, cursor in cursors.items():
        if not cursor.active:
            continue
        src = loaded.get(tid)
        if src is None:
            continue

        # ── Source slice ─────────────────────────────────────────────────────
        if cursor.loop_start_ms is not None and cursor.loop_phrase_ms:
            # Loop mode: cycle the phrase within this chunk, capped at loop_end_ms
            LOOP_XFADE_MS = 16
            phrase_ms = cursor.loop_phrase_ms
            phrase    = src[cursor.loop_source_offset : cursor.loop_source_offset + phrase_ms]
            if len(phrase) == 0:
                continue

            # Crossfade the loop boundary to remove the splice click
            if len(phrase) > LOOP_XFADE_MS * 2:
                tail = phrase[-LOOP_XFADE_MS:]
                head = phrase[:LOOP_XFADE_MS]
                seam = tail.fade_out(LOOP_XFADE_MS).overlay(head.fade_in(LOOP_XFADE_MS))
                phrase = phrase[:-LOOP_XFADE_MS] + seam

            track_chunk = AudioSegment.silent(duration=chunk_ms, frame_rate=target_rate)
            elapsed       = start_ms - cursor.loop_start_ms
            pos_in_phrase = elapsed % phrase_ms
            filled = 0
            loop_fill_end = chunk_ms
            if cursor.loop_end_ms is not None:
                loop_fill_end = max(0, min(chunk_ms, cursor.loop_end_ms - start_ms))
            while filled < loop_fill_end:
                avail = min(phrase_ms - pos_in_phrase, loop_fill_end - filled)
                track_chunk = track_chunk.overlay(
                    phrase[pos_in_phrase : pos_in_phrase + avail], position=filled
                )
                filled       += avail
                pos_in_phrase = 0
            # After loop ends, resume normal playback for the remainder of the chunk
            if loop_fill_end < chunk_ms and cursor.loop_end_ms is not None:
                repeats      = (cursor.loop_end_ms - cursor.loop_start_ms) // phrase_ms
                post_src_pos = cursor.loop_source_offset + phrase_ms * repeats
                post_start   = loop_fill_end
                post_dur     = chunk_ms - post_start
                post_src     = src[post_src_pos : post_src_pos + post_dur]
                if len(post_src) < post_dur:
                    post_src = post_src + AudioSegment.silent(
                        duration=post_dur - len(post_src), frame_rate=target_rate
                    )
                track_chunk = track_chunk.overlay(post_src, position=post_start)
        elif (cursor.fade_in_stems is not None
              and cursor.fade_in_end_ms is not None
              and start_ms < cursor.fade_in_end_ms
              and stem_layers):
            # Stem-blended fade_in: mix individual stems at their specified volumes
            src_start   = cursor.source_pos_ms
            stem_mixed: Optional[AudioSegment] = None
            for stem_name, vol in cursor.fade_in_stems.items():
                sl = stem_layers.get((tid, stem_name))
                if sl is None:
                    continue
                sl_chunk = sl[src_start : src_start + chunk_ms]
                if len(sl_chunk) < chunk_ms:
                    sl_chunk = sl_chunk + AudioSegment.silent(
                        duration=chunk_ms - len(sl_chunk), frame_rate=target_rate
                    )
                if vol > 0:
                    sl_chunk = sl_chunk + float(20 * np.log10(max(vol, 0.001)))
                else:
                    sl_chunk = AudioSegment.silent(duration=chunk_ms, frame_rate=target_rate)
                stem_mixed = sl_chunk if stem_mixed is None else stem_mixed.overlay(sl_chunk)
            if stem_mixed is not None:
                track_chunk = stem_mixed
            else:
                track_chunk = src[src_start : src_start + chunk_ms]
                if len(track_chunk) < chunk_ms:
                    track_chunk = track_chunk + AudioSegment.silent(
                        duration=chunk_ms - len(track_chunk), frame_rate=target_rate
                    )
        else:
            src_start   = cursor.source_pos_ms
            track_chunk = src[src_start : src_start + chunk_ms]
            if len(track_chunk) < chunk_ms:
                track_chunk = track_chunk + AudioSegment.silent(
                    duration=chunk_ms - len(track_chunk), frame_rate=target_rate
                )

        # ── Gain ramps ───────────────────────────────────────────────────────
        if (cursor.fade_in_start_ms is not None
                and cursor.fade_in_end_ms is not None
                and start_ms < cursor.fade_in_end_ms):
            track_chunk = _apply_gain_ramp(
                track_chunk, start_ms,
                cursor.fade_in_start_ms, cursor.fade_in_end_ms,
                0.0, 1.0,
            )

        if (cursor.fade_out_start_ms is not None
                and cursor.fade_out_end_ms is not None
                and start_ms < cursor.fade_out_end_ms):
            track_chunk = _apply_gain_ramp(
                track_chunk, start_ms,
                cursor.fade_out_start_ms, cursor.fade_out_end_ms,
                1.0, 0.0,
            )
            # Hard-silence any tail of this chunk that falls after fade_out_end_ms.
            # The gain ramp reaches 0 exactly at fade_out_end_ms, but the chunk may
            # extend beyond that — without this the gain stays at its last interpolated
            # value rather than being truly silent.
            tail_start = cursor.fade_out_end_ms - start_ms
            if tail_start < chunk_ms:
                silent_tail = AudioSegment.silent(
                    duration=chunk_ms - tail_start, frame_rate=target_rate
                )
                track_chunk = track_chunk[:tail_start] + silent_tail

        # ── Bass cut ─────────────────────────────────────────────────────────
        if cursor.bass_cut:
            track_chunk = high_pass_filter(track_chunk, 200)

        # ── EQ ───────────────────────────────────────────────────────────────
        low, mid, hi = cursor.eq

        # Check whether an EQ action starts inside this chunk (entry boundary case).
        # compute_cursors_at_ms sets cursor.eq only when target_ms >= bar_ms, so a
        # mid-chunk EQ start leaves cursor.eq at unity — we need to detect it here.
        upcoming_eq: Optional[tuple[float, float, float]] = None
        upcoming_eq_start: Optional[int] = None
        if (low, mid, hi) == (1.0, 1.0, 1.0):
            for _a in script.actions:
                if _a.type == "eq" and _a.track == tid:
                    _bar_ms = bars_to_ms(_a.bar or 0, ref_bpm)
                    if start_ms < _bar_ms < end_ms:
                        upcoming_eq = (
                            _a.low  if _a.low  is not None else 1.0,
                            _a.mid  if _a.mid  is not None else 1.0,
                            _a.high if _a.high is not None else 1.0,
                        )
                        upcoming_eq_start = _bar_ms
                        break

        needs_eq = (low, mid, hi) != (1.0, 1.0, 1.0) or upcoming_eq is not None
        if needs_eq:
            eff_low = low if upcoming_eq is None else upcoming_eq[0]
            eff_mid = mid if upcoming_eq is None else upcoming_eq[1]
            eff_hi  = hi  if upcoming_eq is None else upcoming_eq[2]
            orig_chunk = track_chunk          # keep original for crossfade blending
            eq_chunk   = apply_eq(track_chunk, eff_low, eff_mid, eff_hi)
            xf         = EQ_XFADE_MS

            if upcoming_eq_start is not None:
                # Entry boundary mid-chunk: original → EQ over xf ms
                pos      = upcoming_eq_start - start_ms
                fade_len = min(xf, chunk_ms - pos)
                if fade_len > 4:
                    blend = _linear_xfade(orig_chunk[pos:], eq_chunk[pos:], fade_len)
                    track_chunk = orig_chunk[:pos] + blend + eq_chunk[pos + fade_len:]
                else:
                    track_chunk = orig_chunk[:pos] + eq_chunk[pos:]
            else:
                track_chunk = eq_chunk
            # EQ restore (eq_end_ms is never set — restore fires as a new EQ action
            # with low=1.0,mid=1.0,high=1.0 injected by normalizer._restore_incoming_eq.
            # That action is caught by the upcoming_eq detection above, so no extra
            # exit-boundary handling is needed here.


        canvas = canvas.overlay(track_chunk)

    return _apply_soft_limiter(canvas)


def render(script: MixScript, output_path: str, export_mp3: bool = False) -> str:
    """Execute mix script → audio file. Returns output path."""
    track_meta: dict[str, MixTrackRef] = {t.id: t for t in script.tracks}
    ref_bpm = float(np.median([t.bpm for t in script.tracks]))

    # Load, downbeat-trim, and time-stretch all tracks to ref BPM
    print(f"[executor] loading {len(script.tracks)} track(s), ref BPM={ref_bpm:.1f}")
    loaded: dict[str, AudioSegment] = {}
    for t in script.tracks:
        seg = load_track(t.path)
        first_db_ms = int(t.first_downbeat_s * 1000)
        if first_db_ms > 0:
            seg = seg[first_db_ms:]
        seg = time_stretch(seg, t.bpm, ref_bpm)
        loaded[t.id] = seg

    # Normalize all tracks to the same frame rate
    target_rate = loaded[script.tracks[0].id].frame_rate
    for tid in loaded:
        if loaded[tid].frame_rate != target_rate:
            loaded[tid] = loaded[tid].set_frame_rate(target_rate)

    # Pre-load and time-stretch stems for all tracks
    stem_layers: dict[tuple[str, str], AudioSegment] = {}
    for t in script.tracks:
        stem_dir = _stem_dir_for_track(t.id, script)
        found_any = False
        for stem_name in ("drums", "bass", "vocals", "other"):
            path = stem_dir / f"{stem_name}.wav"
            if path.exists():
                seg = AudioSegment.from_wav(str(path))
                seg = time_stretch(seg, t.bpm, ref_bpm)
                if seg.frame_rate != target_rate:
                    seg = seg.set_frame_rate(target_rate)
                stem_layers[(t.id, stem_name)] = seg
                found_any = True
        if not found_any:
            needs_stems = any(
                a.track == t.id and a.type == "fade_in" and a.stems
                for a in script.actions
            )
            if needs_stems:
                print(
                    f"[executor] WARNING: {t.id} has stem fade_in actions but no stems cached "
                    f"at {stem_dir} — stem volumes will be ignored, full mix used instead"
                )

    # Total mix length — scan action timing fields, account for actual track extents
    # from scheduled play positions, then take the max against all loaded audio lengths
    # so a long final track never gets silently truncated.
    max_ms = 0
    for action in script.actions:
        for field in ("at_bar", "start_bar", "bar"):
            val = getattr(action, field, None)
            if val is not None:
                max_ms = max(max_ms, bars_to_ms(val + (action.duration_bars or 0), ref_bpm))
        if action.type in ("play", "fade_in"):
            at_ms_   = bars_to_ms(action.at_bar or action.start_bar or 0, ref_bpm)
            from_ms_ = bars_to_ms(action.from_bar or 0, ref_bpm)
            track_audio = loaded.get(action.track)
            if track_audio is not None:
                remaining = max(0, len(track_audio) - from_ms_)
                max_ms = max(max_ms, at_ms_ + remaining)
    # Safety net: never shorter than the longest loaded track
    max_ms = max(max_ms, max(len(seg) for seg in loaded.values()))
    total_ms = max_ms + bars_to_ms(32, ref_bpm)

    # Per-track layers — each track gets its own AudioSegment, summed at the end.
    # This means fade_out on T1 never touches T2, and EQ on one track can't bleed into another.
    layers: dict[str, AudioSegment] = {
        t.id: AudioSegment.silent(duration=total_ms, frame_rate=target_rate)
        for t in script.tracks
    }

    def sort_key(a: MixAction) -> int:
        candidates = [a.at_bar, a.start_bar, a.bar]
        valid = [b for b in candidates if b is not None]
        return min(valid) if valid else 0

    # Track source position for each track so bass_swap and stem fades use the right offset.
    # Keyed by track id: {"at_ms": int, "from_ms": int}
    active_state: dict[str, dict[str, int]] = {}
    # Track end-time of any active fade_in so the subsequent play can be gated past it.
    fade_in_end: dict[str, int] = {}

    for action in sorted(script.actions, key=sort_key):
        tid = action.track

        if action.type == "play":
            from_ms = bars_to_ms(action.from_bar or 0, ref_bpm)
            at_ms   = bars_to_ms(action.at_bar or 0,   ref_bpm)

            # Guard: clamp play to after the fade_in window. Catches both:
            #   a) play.at_bar < fade_end (Claude placed it too early)
            #   b) play.at_bar == fade_end with from_bar=0 (correct bar, wrong source offset)
            # Use <= so the guard fires even when at_ms == fade_in_end (the common case).
            if tid in fade_in_end and at_ms <= fade_in_end[tid]:
                gap     = fade_in_end[tid] - at_ms
                at_ms   = fade_in_end[tid]
                from_ms = from_ms + gap
                del fade_in_end[tid]

            active_state[tid] = {"at_ms": at_ms, "from_ms": from_ms}
            src = loaded[tid]
            layers[tid] = layers[tid].overlay(src[from_ms:], position=at_ms)

        elif action.type == "fade_in":
            fade_ms  = bars_to_ms(action.duration_bars or 8, ref_bpm)
            at_ms    = bars_to_ms(action.start_bar or 0, ref_bpm)
            from_ms  = bars_to_ms(action.from_bar or 0, ref_bpm)
            active_state[tid] = {"at_ms": at_ms, "from_ms": from_ms}
            fade_in_end[tid]  = at_ms + fade_ms

            if action.stems and stem_layers:
                mixed: Optional[AudioSegment] = None
                for stem_name, vol in action.stems.items():
                    sl = stem_layers.get((tid, stem_name))
                    if sl is None:
                        continue
                    seg = sl[from_ms:from_ms + fade_ms]
                    if vol > 0:
                        seg = seg + float(20 * np.log10(max(vol, 0.001)))
                    else:
                        seg = AudioSegment.silent(duration=len(seg), frame_rate=target_rate)
                    mixed = seg if mixed is None else mixed.overlay(seg)
                if mixed is not None:
                    mixed = _apply_gain_ramp(mixed, 0, 0, fade_ms, 0.0, 1.0)
                    layers[tid] = layers[tid].overlay(mixed, position=at_ms)
            else:
                src  = loaded[tid]
                clip = src[from_ms:from_ms + fade_ms]
                clip = _apply_gain_ramp(clip, 0, 0, fade_ms, 0.0, 1.0)
                layers[tid] = layers[tid].overlay(clip, position=at_ms)

        elif action.type == "fade_out":
            # Apply a gain ramp to the fade window only. Do NOT silence the tail —
            # a subsequent play action on the same track (e.g. loop resume, or a
            # 3-track blend) may legitimately write audio there. Silencing the tail
            # here would erase that audio since fade_out may sort before that play.
            # The silence-after-fade is handled naturally: the gain ramp reaches 0
            # at fade_out_end_ms and the source audio simply plays at zero gain
            # from that point (which is silence). Any later play overlay on the
            # same layer will overwrite that region anyway.
            #
            # Bass is cut by the persistent eq(T1, low=0.0) that the normalizer
            # mandates before every fade_out. No extra HPF needed here.
            fade_ms  = bars_to_ms(action.duration_bars or 8, ref_bpm)
            start_ms = bars_to_ms(action.start_bar or 0, ref_bpm)
            layer    = layers[tid]
            fade_end_ms = start_ms + fade_ms

            chunk = layer[start_ms:fade_end_ms]
            faded = _apply_gain_ramp(chunk, 0, 0, fade_ms, 1.0, 0.0)
            # Replace only the fade window; preserve tail for potential later overlays.
            layers[tid] = (
                layer[:start_ms]
                + faded
                + layer[fade_end_ms:]
            )

        elif action.type == "bass_swap":
            swap_ms = bars_to_ms(action.at_bar or 0, ref_bpm)

            # Cut outgoing bass: crossfade into HPF over 2 bars to avoid click.
            layers[tid] = _apply_smooth_bass_swap(layers[tid], swap_ms, ref_bpm)

            # Restore incoming bass: overlay the bass stem from the correct source position.
            # Bound to the next play action for in_tid so we don't double the bass after
            # the full-track play overlay fires (which already contains bass).
            if action.incoming_track:
                in_tid = action.incoming_track
                bass_stem = stem_layers.get((in_tid, "bass"))
                if bass_stem is not None:
                    if in_tid in active_state:
                        state = active_state[in_tid]
                        stem_offset = state["from_ms"] + (swap_ms - state["at_ms"])
                    else:
                        # bass_swap fires before T2's fade_in — derive offset from the
                        # fade_in action directly rather than a not-yet-populated active_state.
                        fi_action = next(
                            (a for a in script.actions
                             if a.track == in_tid and a.type == "fade_in"),
                            None,
                        )
                        if fi_action is None:
                            bass_stem = None  # no anchor — skip restore
                        else:
                            fi_from_ms = bars_to_ms(fi_action.from_bar or 0, ref_bpm)
                            fi_at_ms   = bars_to_ms(fi_action.start_bar or 0, ref_bpm)
                            # Source position at swap_ms: extrapolate backwards from fade_in anchor.
                            # fi_from_ms is the source offset when fade_in begins at fi_at_ms,
                            # so at mix time swap_ms the source position is:
                            #   fi_from_ms + (swap_ms - fi_at_ms)
                            # When swap_ms < fi_at_ms this is negative — the swap fires before
                            # the track's source audio is in range. Skip the bass restore in that
                            # case rather than clamping to 0 (wrong notes from track beginning).
                            raw_offset = fi_from_ms + (swap_ms - fi_at_ms)
                            if raw_offset < 0:
                                bass_stem = None  # pre-source swap — no restore possible
                            else:
                                stem_offset = raw_offset
                    if bass_stem is not None:
                        stem_offset = max(0, stem_offset)  # safety clamp only
                        bass_tail = bass_stem[stem_offset:]
                        # Find next play action for in_tid after swap_ms
                        next_play_ms: Optional[int] = None
                        for a in script.actions:
                            if a.type == "play" and a.track == in_tid:
                                a_ms = bars_to_ms(a.at_bar or 0, ref_bpm)
                                if a_ms > swap_ms:
                                    if next_play_ms is None or a_ms < next_play_ms:
                                        next_play_ms = a_ms
                        if next_play_ms is not None:
                            bass_tail = bass_tail[:next_play_ms - swap_ms]
                        if len(bass_tail) > 0:
                            layers[in_tid] = layers[in_tid].overlay(bass_tail, position=swap_ms)

        elif action.type == "loop":
            loop_bars     = action.loop_bars or 8
            repeats       = action.loop_repeats or 1
            loop_start_b  = action.start_bar or 0
            loop_start_ms = bars_to_ms(loop_start_b, ref_bpm)

            state = active_state.get(tid)
            if state is None:
                print(f"[executor] WARNING: loop on {tid} at bar {loop_start_b} — no active play, skipping")
                continue

            # Map loop_start in mix time → position in the (already-stretched) source
            offset_in_src = state["from_ms"] + (loop_start_ms - state["at_ms"])
            offset_in_src = max(0, offset_in_src)

            phrase_ms = bars_to_ms(loop_bars, ref_bpm)
            phrase = loaded[tid][offset_in_src:offset_in_src + phrase_ms]
            if len(phrase) == 0:
                print(f"[executor] WARNING: loop on {tid} — phrase slice is empty, skipping")
                continue

            # Crossfade the loop boundary to avoid a click at the splice seam.
            LOOP_XFADE_MS = 16
            if len(phrase) > LOOP_XFADE_MS * 2:
                tail = phrase[-LOOP_XFADE_MS:]
                head = phrase[:LOOP_XFADE_MS]
                seam = tail.fade_out(LOOP_XFADE_MS).overlay(head.fade_in(LOOP_XFADE_MS))
                phrase = phrase[:-LOOP_XFADE_MS] + seam

            loop_end_ms = loop_start_ms + phrase_ms * repeats

            # Mute the original layer under the loop window (default on) so each repeat
            # is a clean replacement, not an additive double.
            if action.loop_mute_tail is not False:
                layer = layers[tid]
                mute_end = min(loop_end_ms, len(layer))
                if loop_start_ms < mute_end:
                    layers[tid] = (
                        layer[:loop_start_ms]
                        + AudioSegment.silent(duration=mute_end - loop_start_ms, frame_rate=target_rate)
                        + layer[mute_end:]
                    )

            for i in range(repeats):
                pos = loop_start_ms + i * phrase_ms
                layers[tid] = layers[tid].overlay(phrase, position=pos)

        elif action.type == "eq":
            # Persistent EQ: applies from `bar` to end of layer (not just a 4-bar window).
            # Real DJs cut channel EQ knobs and hold them — not a momentary dip.
            # The EQ fades in over EQ_XFADE_MS to avoid a click at the cut-in point.
            start_ms_eq = bars_to_ms(action.bar or 0, ref_bpm)
            end_ms_eq   = total_ms  # sustain to end of mix buffer
            chunk_len   = end_ms_eq - start_ms_eq
            if chunk_len <= 0:
                continue

            low  = action.low  if action.low  is not None else 1.0
            mid  = action.mid  if action.mid  is not None else 1.0
            high = action.high if action.high is not None else 1.0

            # Re-read layers[tid] here — a fade_out earlier in this loop may have
            # already mutated it. Using a snapshot captured before the loop would
            # apply EQ to pre-fade audio, not the actual current layer state.
            layer     = layers[tid]
            orig_seg  = layer[start_ms_eq:end_ms_eq]
            eq_seg    = apply_eq(orig_seg, low, mid, high)
            xf        = min(EQ_XFADE_MS, chunk_len // 4)

            if xf > 4:
                # Smooth entry: original → EQ over xf ms
                entry   = _linear_xfade(orig_seg[:xf], eq_seg[:xf], xf)
                blended = entry + eq_seg[xf:]
            else:
                blended = eq_seg

            layers[tid] = layer[:start_ms_eq] + blended

    # Sum all track layers into the final mix
    print("[executor] summing track layers")
    canvas = AudioSegment.silent(duration=total_ms, frame_rate=target_rate)
    for layer in layers.values():
        canvas = canvas.overlay(layer)

    canvas = _apply_soft_limiter(canvas)
    output_path = str(output_path)
    print(f"[executor] exporting to {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if export_mp3 or output_path.endswith(".mp3"):
        canvas.export(output_path, format="mp3", bitrate="320k")
    else:
        canvas.export(output_path, format="wav")

    return output_path


def explain_script(script: MixScript) -> None:
    """Print a human-readable transition table — for tuning without a full render."""
    ref_bpm = float(np.median([t.bpm for t in script.tracks]))
    W = 64

    def bar_to_mmss(bar: int) -> str:
        ms = bars_to_ms(bar, ref_bpm)
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    print("\n" + "─" * W)
    print(f"  {script.mix_title}")
    print(f"  ref BPM: {ref_bpm:.1f}")
    print("─" * W)

    plays      = {a.track: a for a in script.actions if a.type == "play"}
    fade_ins   = {a.track: a for a in script.actions if a.type == "fade_in"}
    fade_outs  = {a.track: a for a in script.actions if a.type == "fade_out"}
    bass_swaps = [a for a in script.actions if a.type == "bass_swap"]
    loops      = [a for a in script.actions if a.type == "loop"]
    eqs        = [a for a in script.actions if a.type == "eq"]

    for t in script.tracks:
        pl = plays.get(t.id)
        fi = fade_ins.get(t.id)
        fo = fade_outs.get(t.id)

        start_bar = pl.at_bar if pl else (fi.start_bar if fi else 0)
        from_bar  = pl.from_bar if pl else (fi.from_bar if fi else 0)
        out_bar   = fo.start_bar if fo else None
        out_dur   = fo.duration_bars if fo else None

        start_ts = bar_to_mmss(start_bar or 0)
        out_str  = f"bar {out_bar} ({out_dur}b → {bar_to_mmss((out_bar or 0) + (out_dur or 0))})" if out_bar is not None else "—"

        stem_str = ""
        if fi and fi.stems:
            parts = [f"{k}:{v:.1f}" for k, v in fi.stems.items() if v != 1.0]
            stem_str = f"  stems={{{', '.join(parts)}}}" if parts else ""
        fi_str = f"fade_in bar {fi.start_bar} dur={fi.duration_bars}b{stem_str}" if fi else "direct play"

        print(f"\n  {t.id}  BPM={t.bpm}  start@bar {start_bar} ({start_ts})"
              f"  from_bar={from_bar}")
        print(f"       in: {fi_str}")
        print(f"       out: fade_out@{out_str}")

    if bass_swaps or loops or eqs:
        print("\n  Events:")
        for bs in sorted(bass_swaps, key=lambda a: a.at_bar or 0):
            swap_ts = bar_to_mmss(bs.at_bar or 0)
            inc = f" → restore {bs.incoming_track}" if bs.incoming_track else ""
            print(f"    bass_swap  bar {bs.at_bar} ({swap_ts})  cut {bs.track}{inc}")
        for lp in sorted(loops, key=lambda a: a.start_bar or 0):
            lp_ts  = bar_to_mmss(lp.start_bar or 0)
            lp_end = (lp.start_bar or 0) + (lp.loop_bars or 8) * (lp.loop_repeats or 1)
            mute   = "" if lp.loop_mute_tail is False else " mute_tail"
            print(f"    loop       bar {lp.start_bar} ({lp_ts})  {lp.track}  "
                  f"{lp.loop_bars}b × {lp.loop_repeats}  → end bar {lp_end}{mute}")
        for eq in sorted(eqs, key=lambda a: a.bar or 0):
            print(f"    eq         bar {eq.bar}  {eq.track}  low={eq.low} mid={eq.mid} hi={eq.high}")

    # Overlap windows — pair by temporal intersection, not "first other track"
    fi_list  = sorted(fade_ins.values(),  key=lambda a: a.start_bar or 0)
    fo_list  = sorted(fade_outs.values(), key=lambda a: a.start_bar or 0)
    if fi_list:
        print("\n  Transitions:")
        for fi in fi_list:
            fi_start = fi.start_bar or 0
            fi_end   = fi_start + (fi.duration_bars or 0)
            # find fade_out from a different track whose window intersects
            fo = next(
                (fo for fo in fo_list
                 if fo.track != fi.track
                 and (fo.start_bar or 0) < fi_end
                 and fi_start < (fo.start_bar or 0) + (fo.duration_bars or 0)),
                None,
            )
            if fo:
                fo_start = fo.start_bar or 0
                fo_end   = fo_start + (fo.duration_bars or 0)
                overlap_start = min(fi_start, fo_start)
                overlap_end   = max(fi_end, fo_end)
                overlap_bars  = overlap_end - overlap_start
                print(f"    {fo.track}→{fi.track}  overlap bars {overlap_start}–{overlap_end}"
                      f"  ({overlap_bars} bars, {bar_to_mmss(overlap_start)}–{bar_to_mmss(overlap_end)})")

    last_bar = max(
        (a.at_bar or a.start_bar or a.bar or 0) + (a.duration_bars or 0)
        for a in script.actions
    )
    est_s = bars_to_ms(last_bar, ref_bpm) // 1000
    print(f"\n  Est. length: {est_s // 60}m {est_s % 60:02d}s  (last scheduled bar: {last_bar})")
    print("─" * W + "\n")
