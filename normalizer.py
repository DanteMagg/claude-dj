"""
Safety layer between mix_director output and executor.
Claude designs the *when*; this enforces the *how* stays in known-safe ranges.
"""
from __future__ import annotations

import dataclasses

from schema import MixAction, MixScript

DURATION_MIN = 4    # bars — absolute floor (safety clamp only)
DURATION_MAX = 64   # bars — absolute ceiling
DURATION_PREFERRED_MIN = 16  # biases club transitions toward 16+ bars
PHRASE = 8          # bar granularity for snapping and bass_swap injection


def normalize(script: MixScript) -> MixScript:
    actions = list(script.actions)
    actions = _clamp_durations(actions)
    actions = _clamp_eq(actions)
    actions = _inject_play_for_orphaned_fade_in(actions)
    actions = _inject_bass_swap_if_missing(actions)
    return MixScript(
        mix_title=script.mix_title,
        reasoning=script.reasoning,
        tracks=script.tracks,
        actions=actions,
    )


def _snap_duration_to_phrase(bars: int) -> int:
    """Round to nearest phrase multiple, then enforce preferred floor."""
    snapped = round(bars / PHRASE) * PHRASE
    snapped = max(PHRASE, snapped)           # never below one phrase
    return max(snapped, DURATION_PREFERRED_MIN)


def _clamp_durations(actions: list[MixAction]) -> list[MixAction]:
    result = []
    for a in actions:
        if a.duration_bars is not None:
            clamped = max(DURATION_MIN, min(DURATION_MAX, a.duration_bars))
            if a.type in ("fade_in", "fade_out"):
                clamped = _snap_duration_to_phrase(clamped)
            a = dataclasses.replace(a, duration_bars=clamped)
        result.append(a)
    return result


def _clamp_eq(actions: list[MixAction]) -> list[MixAction]:
    """Clamp eq fields to [0.0, 1.0]. apply_eq maps mid to ±6 dB — that's already the ceiling."""
    result = []
    for a in actions:
        if a.type != "eq":
            result.append(a)
            continue
        result.append(dataclasses.replace(
            a,
            low=max(0.0, min(1.0, a.low if a.low is not None else 1.0)),
            mid=max(0.0, min(1.0, a.mid if a.mid is not None else 1.0)),
            high=max(0.0, min(1.0, a.high if a.high is not None else 1.0)),
        ))
    return result


def _action_sort_key(a: MixAction) -> int:
    candidates = [a.at_bar, a.start_bar, a.bar]
    valid = [b for b in candidates if b is not None]
    return min(valid) if valid else 0


def _find_all_transitions(
    actions: list[MixAction],
) -> list[tuple[int, int, str, str]]:
    """
    Return one tuple per (fade_out, fade_in) pair from different tracks whose time
    windows overlap: (overlap_start_bar, overlap_end_bar, outgoing_tid, incoming_tid).
    Handles any number of transitions in one pass — safe for 3+ track sets.
    """
    fade_ins  = [a for a in actions if a.type == "fade_in"]
    fade_outs = [a for a in actions if a.type == "fade_out"]

    transitions = []
    for fi in fade_ins:
        fi_start = fi.start_bar or 0
        fi_end   = fi_start + (fi.duration_bars or 0)
        for fo in fade_outs:
            if fo.track == fi.track:
                continue
            fo_start = fo.start_bar or 0
            fo_end   = fo_start + (fo.duration_bars or 0)
            if fo_start < fi_end and fi_start < fo_end:  # windows intersect
                transitions.append((
                    min(fi_start, fo_start),
                    max(fi_end, fo_end),
                    fo.track,   # outgoing
                    fi.track,   # incoming
                ))
    return transitions


def _inject_play_for_orphaned_fade_in(actions: list[MixAction]) -> list[MixAction]:
    """
    If a track has a fade_in but no play action at or after the fade window ends,
    auto-inject a play so the track doesn't go silent after the intro.
    """
    injected = []
    for fi in actions:
        if fi.type != "fade_in":
            continue
        fade_end_bar = (fi.start_bar or 0) + (fi.duration_bars or 0)
        has_play = any(
            a.type == "play" and a.track == fi.track and (a.at_bar or 0) >= (fi.start_bar or 0)
            for a in actions
        )
        if not has_play:
            from_bar = (fi.from_bar or 0) + (fi.duration_bars or 0)
            injected.append(
                MixAction(type="play", track=fi.track, at_bar=fade_end_bar, from_bar=from_bar)
            )
            print(
                f"[normalizer] injected implied play for {fi.track} at bar {fade_end_bar} "
                f"(from_bar={from_bar}) — no play followed its fade_in"
            )
    if not injected:
        return actions
    return sorted(actions + injected, key=_action_sort_key)


def _inject_bass_swap_if_missing(actions: list[MixAction]) -> list[MixAction]:
    """
    For every detected transition window, ensure exactly one bass_swap exists and
    that it carries incoming_track. Works for any number of transitions (3+ tracks).
    """
    transitions = _find_all_transitions(actions)
    if not transitions:
        return actions

    patched  = list(actions)
    injected: list[MixAction] = []

    for overlap_start, overlap_end, outgoing, incoming in transitions:
        swaps_in_window = [
            a for a in patched
            if a.type == "bass_swap"
            and a.track == outgoing
            and overlap_start <= (a.at_bar or a.bar or 0) <= overlap_end
        ]

        if swaps_in_window:
            # Backfill incoming_track where absent
            new_patched = []
            for a in patched:
                if (
                    a.type == "bass_swap"
                    and a.track == outgoing
                    and overlap_start <= (a.at_bar or a.bar or 0) <= overlap_end
                    and a.incoming_track is None
                ):
                    a = dataclasses.replace(a, incoming_track=incoming)
                new_patched.append(a)
            patched = new_patched
        else:
            # Inject at nearest phrase boundary to window midpoint
            mid = (overlap_start + overlap_end) // 2
            swap_bar = round(mid / PHRASE) * PHRASE
            swap_bar = max(overlap_start, min(swap_bar, overlap_end))
            injected.append(MixAction(
                type="bass_swap", track=outgoing, at_bar=swap_bar, incoming_track=incoming,
            ))

    if injected:
        return sorted(patched + injected, key=_action_sort_key)
    return patched
