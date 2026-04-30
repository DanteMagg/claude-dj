from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from pydub import AudioSegment
from pydub.effects import high_pass_filter, low_pass_filter

from schema import MixAction, MixScript, MixTrackRef


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
            samples = samples.reshape(-1, 2).T  # (2, N)
        sr = audio.frame_rate
        stretched = pyrb.time_stretch(samples, sr, ratio)
        if audio.channels == 2:
            out = np.clip(stretched.T.flatten() * max_val, -max_val, max_val - 1).astype(np.int16)
        else:
            out = np.clip(stretched * max_val, -max_val, max_val - 1).astype(np.int16)
        return audio._spawn(out.tobytes())
    except Exception:
        # fallback: pydub frame_rate trick (changes pitch but keeps duration ratio)
        new_frame_rate = int(audio.frame_rate * ratio)
        return audio._spawn(audio.raw_data, overrides={"frame_rate": new_frame_rate}).set_frame_rate(audio.frame_rate)


def apply_eq(audio: AudioSegment, low: float, mid: float, high: float) -> AudioSegment:
    """Approximate EQ via filter chain. mid gain applied as volume."""
    result = audio
    if low < 0.5:
        result = high_pass_filter(result, 200)
    if high < 0.5:
        result = low_pass_filter(result, 8000)
    if mid != 1.0:
        result = result + (20 * (mid - 1.0))  # rough dB adjust
    return result


def overlay_stems(
    stem_dir: Path,
    duration_ms: int,
    stem_volumes: dict[str, float],
) -> Optional[AudioSegment]:
    """Load individual stems and mix them at specified volumes. Returns None if stems unavailable."""
    result: Optional[AudioSegment] = None
    for stem_name, vol in stem_volumes.items():
        stem_path = stem_dir / f"{stem_name}.wav"
        if not stem_path.exists():
            continue
        seg = AudioSegment.from_wav(str(stem_path))[:duration_ms]
        seg = seg + (20 * np.log10(max(vol, 0.001)))  # volume in dB
        result = seg if result is None else result.overlay(seg)
    return result


def render(script: MixScript, output_path: str, export_mp3: bool = False) -> str:
    """Execute mix script → audio file. Returns output path."""
    # resolve track BPMs and first-downbeat offsets
    track_meta: dict[str, MixTrackRef] = {t.id: t for t in script.tracks}

    # pick a reference BPM (median) to time-stretch everything to
    bpms = [t.bpm for t in script.tracks]
    ref_bpm = float(np.median(bpms))

    # Load and time-stretch all tracks
    print(f"[executor] loading {len(script.tracks)} track(s), ref BPM={ref_bpm:.1f}")
    loaded: dict[str, AudioSegment] = {}
    for t in script.tracks:
        seg = load_track(t.path)
        # trim to first downbeat (align bar grid)
        first_db_ms = int(t.first_downbeat_s * 1000)
        if first_db_ms > 0:
            seg = seg[first_db_ms:]
        seg = time_stretch(seg, t.bpm, ref_bpm)
        loaded[t.id] = seg

    bar_ms = bars_to_ms(1, ref_bpm)

    # Estimate total mix length from actions
    max_bar = 0
    for action in script.actions:
        for bar_field in ("at_bar", "start_bar", "bar"):
            val = getattr(action, bar_field, None)
            if val is not None:
                max_bar = max(max_bar, val + (action.duration_bars or 0))

    total_ms = bars_to_ms(max_bar + 32, ref_bpm)
    canvas = AudioSegment.silent(duration=total_ms)

    active_tracks: dict[str, dict] = {}  # track_id -> {play_bar, from_bar, playing: bool}
    eq_state: dict[str, dict] = {}

    # Sort actions by their earliest bar reference
    def action_bar(a: MixAction) -> int:
        return min(
            x for x in [a.at_bar, a.start_bar, a.bar] if x is not None
        ) if any(x is not None for x in [a.at_bar, a.start_bar, a.bar]) else 0

    sorted_actions = sorted(script.actions, key=action_bar)

    for action in sorted_actions:
        tid = action.track
        meta = track_meta[tid]

        if action.type == "play":
            active_tracks[tid] = {
                "play_bar": action.at_bar,
                "from_bar": action.from_bar,
            }
            src = loaded[tid]
            from_ms = bars_to_ms(action.from_bar or 0, ref_bpm)
            at_ms = bars_to_ms(action.at_bar or 0, ref_bpm)
            clip = src[from_ms:]
            canvas = canvas.overlay(clip, position=at_ms)

        elif action.type == "fade_in":
            fade_ms = bars_to_ms(action.duration_bars or 8, ref_bpm)
            at_ms = bars_to_ms(action.start_bar or 0, ref_bpm)

            if action.stems:
                # stem-selective fade: rebuild the incoming track from stems
                stem_dir = _stem_dir_for_track(tid, script)
                mixed = overlay_stems(stem_dir, fade_ms, action.stems)
                if mixed is not None:
                    faded = mixed.fade_in(fade_ms)
                    canvas = canvas.overlay(faded, position=at_ms)
                    continue

            src = loaded[tid]
            from_ms = bars_to_ms(active_tracks.get(tid, {}).get("from_bar", 0), ref_bpm)
            clip = src[from_ms:from_ms + fade_ms].fade_in(fade_ms)
            canvas = canvas.overlay(clip, position=at_ms)

        elif action.type == "fade_out":
            fade_ms = bars_to_ms(action.duration_bars or 8, ref_bpm)
            at_ms = bars_to_ms(action.start_bar or 0, ref_bpm)
            faded = canvas[at_ms:at_ms + fade_ms].fade_out(fade_ms)
            # silence the tail so subsequent play actions for other tracks overlay onto quiet
            rest_ms = max(0, len(canvas) - at_ms - fade_ms)
            canvas = (
                canvas[:at_ms]
                + faded
                + AudioSegment.silent(duration=rest_ms, frame_rate=canvas.frame_rate)
            )

        elif action.type == "eq":
            bar_ms_pos = bars_to_ms(action.bar or 0, ref_bpm)
            low = action.low if action.low is not None else 1.0
            mid = action.mid if action.mid is not None else 1.0
            high = action.high if action.high is not None else 1.0
            # apply EQ to one bar's worth of canvas at that position
            chunk = canvas[bar_ms_pos:bar_ms_pos + bar_ms]
            eq_chunk = apply_eq(chunk, low, mid, high)
            canvas = canvas[:bar_ms_pos] + eq_chunk + canvas[bar_ms_pos + bar_ms:]

    output_path = str(output_path)
    print(f"[executor] exporting to {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if export_mp3 or output_path.endswith(".mp3"):
        canvas.export(output_path, format="mp3", bitrate="320k")
    else:
        canvas.export(output_path, format="wav")

    return output_path


def _stem_dir_for_track(track_id: str, script: MixScript) -> Path:
    """Find the stems directory for a given track id."""
    for t in script.tracks:
        if t.id == track_id:
            # stems are next to the track file in cache/<hash>/stems/
            from analyze import file_hash
            h = file_hash(t.path)
            return Path(__file__).parent / "cache" / h / "stems"
    return Path("/nonexistent")
