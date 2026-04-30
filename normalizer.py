"""
Safety layer between mix_director output and executor.
Claude designs the *when*; this enforces the *how* stays in known-safe ranges.
"""
from __future__ import annotations

import dataclasses

from schema import MixAction, MixScript

DURATION_MIN = 4    # bars — shortest legal fade
DURATION_MAX = 64   # bars — longest legal fade
PHRASE = 8          # bar granularity for bass_swap injection


def normalize(script: MixScript) -> MixScript:
    actions = list(script.actions)
    actions = _clamp_durations(actions)
    actions = _clamp_eq(actions)
    actions = _inject_bass_swap_if_missing(actions)
    return MixScript(
        mix_title=script.mix_title,
        reasoning=script.reasoning,
        tracks=script.tracks,
        actions=actions,
    )


def _clamp_durations(actions: list[MixAction]) -> list[MixAction]:
    result = []
    for a in actions:
        if a.duration_bars is not None:
            clamped = max(DURATION_MIN, min(DURATION_MAX, a.duration_bars))
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


def _find_transition(actions: list[MixAction]) -> tuple[int | None, int | None, str | None]:
    """Return (overlap_start_bar, overlap_end_bar, outgoing_track_id), or all None."""
    fade_in  = next((a for a in actions if a.type == "fade_in"),  None)
    fade_out = next((a for a in actions if a.type == "fade_out"), None)
    if not fade_in or not fade_out:
        return None, None, None

    fi_start = fade_in.start_bar or 0
    fi_end   = fi_start + (fade_in.duration_bars or 0)
    fo_start = fade_out.start_bar or 0
    fo_end   = fo_start + (fade_out.duration_bars or 0)

    return min(fi_start, fo_start), max(fi_end, fo_end), fade_out.track


def _action_sort_key(a: MixAction) -> int:
    candidates = [a.at_bar, a.start_bar, a.bar]
    valid = [b for b in candidates if b is not None]
    return min(valid) if valid else 0


def _inject_bass_swap_if_missing(actions: list[MixAction]) -> list[MixAction]:
    overlap_start, overlap_end, outgoing = _find_transition(actions)
    if overlap_start is None:
        return actions

    has_swap = any(
        a.type == "bass_swap"
        and overlap_start <= (a.at_bar or a.bar or 0) <= overlap_end
        for a in actions
    )
    if has_swap:
        return actions

    mid = (overlap_start + overlap_end) // 2
    # Round to nearest phrase boundary (not floor — avoids always picking the start)
    swap_bar = round(mid / PHRASE) * PHRASE
    swap_bar = max(overlap_start, min(swap_bar, overlap_end))

    swap = MixAction(type="bass_swap", track=outgoing, at_bar=swap_bar)
    return sorted(actions + [swap], key=_action_sort_key)
