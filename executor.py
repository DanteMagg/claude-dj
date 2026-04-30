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

    for action in sorted(script.actions, key=sort_key):
        tid = action.track

        if action.type == "play":
            from_ms = bars_to_ms(action.from_bar or 0, ref_bpm)
            at_ms   = bars_to_ms(action.at_bar or 0,   ref_bpm)
            active_state[tid] = {"at_ms": at_ms, "from_ms": from_ms}
            src = loaded[tid]
            layers[tid] = layers[tid].overlay(src[from_ms:], position=at_ms)

        elif action.type == "fade_in":
            fade_ms  = bars_to_ms(action.duration_bars or 8, ref_bpm)
            at_ms    = bars_to_ms(action.start_bar or 0, ref_bpm)
            from_ms  = bars_to_ms(action.from_bar or 0, ref_bpm)
            active_state[tid] = {"at_ms": at_ms, "from_ms": from_ms}

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
                    layers[tid] = layers[tid].overlay(mixed.fade_in(fade_ms), position=at_ms)
            else:
                src = loaded[tid]
                clip = src[from_ms:from_ms + fade_ms].fade_in(fade_ms)
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
            swap_ms = bars_to_ms(action.at_bar or 0, ref_bpm)

            # Cut outgoing bass: high-pass the outgoing track's tail from swap_ms onward.
            layer = layers[tid]
            if swap_ms < len(layer):
                tail = high_pass_filter(layer[swap_ms:], 200)
                layers[tid] = layer[:swap_ms] + tail

            # Restore incoming bass: overlay the bass stem from the correct source position.
            if action.incoming_track:
                in_tid = action.incoming_track
                bass_stem = stem_layers.get((in_tid, "bass"))
                if bass_stem is not None and in_tid in active_state:
                    state = active_state[in_tid]
                    # How far into the source is the incoming track at swap_ms?
                    stem_offset = state["from_ms"] + (swap_ms - state["at_ms"])
                    stem_offset = max(0, stem_offset)
                    bass_tail = bass_stem[stem_offset:]
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
