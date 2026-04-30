from __future__ import annotations

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


def apply_eq(audio: AudioSegment, low: float, mid: float, high: float) -> AudioSegment:
    """
    Gentle 3-band EQ approximation.
    low/high: 0.0 = full filter kill, 1.0 = bypass.
    mid: 0.0–1.0 mapped to −6…+6 dB.
    """
    low  = max(0.0, min(low,  1.0))
    mid  = max(0.0, min(mid,  1.0))
    high = max(0.0, min(high, 1.0))

    result = audio
    if low < 0.5:
        result = high_pass_filter(result, 200)
    if high < 0.5:
        result = low_pass_filter(result, 8000)
    if mid != 1.0:
        gain_db = max(-6.0, min(6.0, 12.0 * (mid - 0.5)))
        result = result + gain_db
    return result


def _stem_dir_for_track(track_id: str, script: MixScript) -> Path:
    for t in script.tracks:
        if t.id == track_id:
            from analyze import file_hash
            h = file_hash(t.path)
            return Path(__file__).parent / "cache" / h / "stems"
    return Path("/nonexistent")


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
        for stem_name in ("drums", "bass", "vocals", "other"):
            path = stem_dir / f"{stem_name}.wav"
            if path.exists():
                seg = AudioSegment.from_wav(str(path))
                seg = time_stretch(seg, t.bpm, ref_bpm)
                if seg.frame_rate != target_rate:
                    seg = seg.set_frame_rate(target_rate)
                stem_layers[(t.id, stem_name)] = seg

    # Total mix length
    max_bar = 0
    for action in script.actions:
        for field in ("at_bar", "start_bar", "bar"):
            val = getattr(action, field, None)
            if val is not None:
                max_bar = max(max_bar, val + (action.duration_bars or 0))
    total_ms = bars_to_ms(max_bar + 32, ref_bpm)

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

    for action in sorted(script.actions, key=sort_key):
        tid = action.track

        if action.type == "play":
            src = loaded[tid]
            from_ms = bars_to_ms(action.from_bar or 0, ref_bpm)
            at_ms   = bars_to_ms(action.at_bar or 0,   ref_bpm)
            layers[tid] = layers[tid].overlay(src[from_ms:], position=at_ms)

        elif action.type == "fade_in":
            fade_ms = bars_to_ms(action.duration_bars or 8, ref_bpm)
            at_ms   = bars_to_ms(action.start_bar or 0, ref_bpm)

            if action.stems and stem_layers:
                mixed: Optional[AudioSegment] = None
                for stem_name, vol in action.stems.items():
                    sl = stem_layers.get((tid, stem_name))
                    if sl is None:
                        continue
                    seg = sl[:fade_ms]
                    if vol > 0:
                        seg = seg + float(20 * np.log10(max(vol, 0.001)))
                    else:
                        seg = AudioSegment.silent(duration=len(seg), frame_rate=target_rate)
                    mixed = seg if mixed is None else mixed.overlay(seg)
                if mixed is not None:
                    layers[tid] = layers[tid].overlay(mixed.fade_in(fade_ms), position=at_ms)
            else:
                src = loaded[tid]
                clip = src[:fade_ms].fade_in(fade_ms)
                layers[tid] = layers[tid].overlay(clip, position=at_ms)

        elif action.type == "fade_out":
            # Track-local: fades and silences only this track's layer.
            fade_ms  = bars_to_ms(action.duration_bars or 8, ref_bpm)
            start_ms = bars_to_ms(action.start_bar or 0, ref_bpm)
            layer    = layers[tid]
            faded    = layer[start_ms:start_ms + fade_ms].fade_out(fade_ms)
            silence_ms = max(0, len(layer) - start_ms - fade_ms)
            layers[tid] = (
                layer[:start_ms]
                + faded
                + AudioSegment.silent(duration=silence_ms, frame_rate=target_rate)
            )

        elif action.type == "bass_swap":
            # Hard high-pass on the outgoing track from this bar onward — kills bass bleed.
            swap_ms = bars_to_ms(action.at_bar or 0, ref_bpm)
            layer = layers[tid]
            if swap_ms < len(layer):
                tail = high_pass_filter(layer[swap_ms:], 200)
                layers[tid] = layer[:swap_ms] + tail

        elif action.type == "eq":
            # Apply EQ over a 4-bar window centered on action.bar for a gradual effect.
            center_ms   = bars_to_ms(action.bar or 0, ref_bpm)
            half_span   = bars_to_ms(2, ref_bpm)
            start_ms    = max(0, center_ms - half_span)
            end_ms      = min(total_ms, center_ms + half_span)

            low  = action.low  if action.low  is not None else 1.0
            mid  = action.mid  if action.mid  is not None else 1.0
            high = action.high if action.high is not None else 1.0

            layer = layers[tid]
            chunk = apply_eq(layer[start_ms:end_ms], low, mid, high)
            layers[tid] = layer[:start_ms] + chunk + layer[end_ms:]

    # Sum all track layers into the final mix
    print("[executor] summing track layers")
    canvas = AudioSegment.silent(duration=total_ms, frame_rate=target_rate)
    for layer in layers.values():
        canvas = canvas.overlay(layer)

    output_path = str(output_path)
    print(f"[executor] exporting to {output_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if export_mp3 or output_path.endswith(".mp3"):
        canvas.export(output_path, format="mp3", bitrate="320k")
    else:
        canvas.export(output_path, format="wav")

    return output_path
