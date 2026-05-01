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
    actions = _clamp_loops(actions)
    actions = _inject_play_for_orphaned_fade_in(actions)
    actions = _inject_bass_swap_if_missing(actions)
    actions = _inject_fade_out_if_missing(actions, script.tracks)
    actions = _restore_incoming_eq(actions)
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


def _clamp_loops(actions: list[MixAction]) -> list[MixAction]:
    """Snap loop_bars and start_bar to phrase multiples; cap loop_repeats to [1, 4]."""
    result = []
    for a in actions:
        if a.type != "loop":
            result.append(a)
            continue
        lb = a.loop_bars or PHRASE
        lb = max(PHRASE // 2, round(lb / PHRASE) * PHRASE)
        reps = max(1, min(4, a.loop_repeats or 1))
        # start_bar must be a phrase boundary — floor to nearest multiple of PHRASE
        start = (a.start_bar or 0) // PHRASE * PHRASE
        result.append(dataclasses.replace(a, loop_bars=lb, loop_repeats=reps, start_bar=start))
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


def _inject_fade_out_if_missing(
    actions: list[MixAction],
    tracks: list,
) -> list[MixAction]:
    """
    Every non-final track must have a fade_out scheduled. If one is absent, auto-inject
    one at the last play action's at_bar + 16 bars (phrase-snapped), then silence the rest.
    This is a last-resort safety net — the prompt should have produced one explicitly.
    """
    if len(tracks) < 2:
        return actions

    non_final_tids = {t.id for t in tracks[:-1]}
    injected: list[MixAction] = []

    for tid in non_final_tids:
        has_fade_out = any(a.type == "fade_out" and a.track == tid for a in actions)
        if has_fade_out:
            continue

        # Find the latest play or fade_in action for this track to anchor on
        track_actions = [
            a for a in actions
            if a.track == tid and a.type in ("play", "fade_in")
        ]
        if not track_actions:
            continue

        anchor = max(track_actions, key=lambda a: a.at_bar or a.start_bar or 0)
        anchor_bar = anchor.at_bar or anchor.start_bar or 0
        fade_start = ((anchor_bar + 16) // PHRASE) * PHRASE
        injected.append(MixAction(
            type="fade_out", track=tid,
            start_bar=fade_start,
            duration_bars=16,
        ))
        print(
            f"[normalizer] auto-injected fade_out for {tid} at bar {fade_start} "
            f"(anchored on {anchor.type}@{anchor_bar}) — was missing"
        )

    if not injected:
        return actions
    return sorted(actions + injected, key=_action_sort_key)


def _restore_incoming_eq(actions: list[MixAction]) -> list[MixAction]:
    """
    EQ is now persistent (from bar → end of track). That's correct for the outgoing
    track (T1), which is fading out and disappears. It's destructive for the incoming
    track (T2), which continues playing after the blend: any bass/mid cut applied during
    the overlap window would color T2 for the rest of the mix.

    Fix: for every eq action on a track that has a fade_in (incoming) but no fade_out
    (i.e. it continues past the transition), inject a restore eq(low=1.0, mid=1.0,
    high=1.0) at the end of the transition window.
    """
    incoming_tids = {
        a.track for a in actions if a.type == "fade_in"
    }
    outgoing_tids = {
        a.track for a in actions if a.type == "fade_out"
    }
    # Tracks that are incoming-only (not also exiting in this sub-script).
    # These are the continuing tracks whose EQ must not persist.
    continuing_tids = incoming_tids - outgoing_tids

    injected: list[MixAction] = []
    for a in actions:
        if a.type != "eq" or a.track not in continuing_tids:
            continue
        # This EQ is on a track that continues playing — find the transition end bar.
        # Use the fade_in for that track to determine when the blend window closes.
        fi = next(
            (x for x in actions if x.type == "fade_in" and x.track == a.track),
            None,
        )
        if fi is None:
            continue
        eq_any_non_default = (
            (a.low  is not None and a.low  != 1.0) or
            (a.mid  is not None and a.mid  != 1.0) or
            (a.high is not None and a.high != 1.0)
        )
        if not eq_any_non_default:
            continue  # eq is already unity — no restore needed
        restore_bar = (fi.start_bar or 0) + (fi.duration_bars or 0)
        restore_bar = round(restore_bar / PHRASE) * PHRASE
        # Only inject if there isn't already a restore at or after this bar
        already_restored = any(
            x.type == "eq" and x.track == a.track
            and (x.bar or 0) >= restore_bar
            and x.low == 1.0 and x.mid == 1.0 and x.high == 1.0
            for x in actions
        )
        if not already_restored:
            injected.append(MixAction(
                type="eq", track=a.track,
                bar=restore_bar,
                low=1.0, mid=1.0, high=1.0,
            ))
            print(
                f"[normalizer] restored EQ for incoming {a.track} at bar {restore_bar} "
                f"(had low={a.low} mid={a.mid} high={a.high} from bar {a.bar})"
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
