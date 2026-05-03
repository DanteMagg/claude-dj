"""
Safety layer between mix_director output and executor.
Claude designs the *when*; this enforces the *how* stays in known-safe ranges.
"""
from __future__ import annotations

import dataclasses
import logging

from schema import MixAction, MixScript

logger = logging.getLogger("normalizer")

DURATION_MIN = 4    # bars — absolute floor (safety clamp only)
DURATION_MAX = 64   # bars — absolute ceiling
DURATION_PREFERRED_MIN = 16  # biases club transitions toward 16+ bars
PHRASE = 8          # bar granularity for snapping and bass_swap injection


def normalize(script: MixScript) -> MixScript:
    before = list(script.actions)
    logger.debug(
        "normalize() called: %d actions, %d tracks",
        len(before), len(script.tracks),
    )
    actions = list(script.actions)
    actions = _clamp_durations(actions)
    actions = _clamp_eq(actions)
    actions = _clamp_loops(actions)
    actions = _enforce_t2_bass_zero(actions)
    actions = _inject_eq_duration(actions)
    actions = _snap_fade_in_anchor(actions)
    actions = _snap_bass_swap_bars(actions)
    actions = _align_crossfade_starts(actions)
    actions = _fix_play_from_bar_after_fade_in(actions)
    actions = _inject_play_for_orphaned_fade_in(actions)
    actions = _inject_bass_swap_if_missing(actions)
    actions = _inject_fade_out_if_missing(actions, script.tracks)
    actions = _ramp_stems_release(actions)
    actions = _restore_incoming_eq(actions)

    added   = [a for a in actions if a not in before]
    removed = [a for a in before  if a not in actions]
    if added or removed:
        logger.debug(
            "normalize() changes: +%d injected, -%d removed\n"
            "  injected: %s\n"
            "  removed:  %s",
            len(added), len(removed),
            [f"{a.type}({a.track})" for a in added],
            [f"{a.type}({a.track})" for a in removed],
        )
    else:
        logger.debug("normalize(): no structural changes (actions look clean)")

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
        if a.type in ("fade_in", "fade_out") and a.duration_bars is None:
            msg = f"set missing duration_bars={DURATION_PREFERRED_MIN} on {a.type}({a.track})"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, duration_bars=DURATION_PREFERRED_MIN)
        if a.duration_bars is not None:
            clamped = max(DURATION_MIN, min(DURATION_MAX, a.duration_bars))
            if a.type in ("fade_in", "fade_out"):
                clamped = _snap_duration_to_phrase(clamped)
            a = dataclasses.replace(a, duration_bars=clamped)
        result.append(a)
    return result


_VALID_LOOP_BARS = (1, 2, 4, 8, 16, 32)


def _snap_loop_bars(bars: int) -> int:
    """Snap to nearest valid loop length. Minimum is 1 bar."""
    bars = max(1, bars)
    return min(_VALID_LOOP_BARS, key=lambda v: (abs(v - bars), -v))


def _clamp_loops(actions: list[MixAction]) -> list[MixAction]:
    """Snap loop_bars to valid values; cap loop_repeats to [1, 8]."""
    result = []
    for a in actions:
        if a.type != "loop":
            result.append(a)
            continue
        lb = _snap_loop_bars(a.loop_bars or 4)
        reps = max(1, min(8, a.loop_repeats or 1))
        start = (a.start_bar or 0) // lb * lb  # align to loop_bars boundary
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


def _enforce_t2_bass_zero(actions: list[MixAction]) -> list[MixAction]:
    """T2's fade_in must never introduce bass. Force stems["bass"]=0.0 if set."""
    result = []
    for a in actions:
        if a.type == "fade_in" and a.stems and a.stems.get("bass", 0.0) > 0.0:
            msg = f"forced stems.bass=0.0 on fade_in({a.track}) (was {a.stems['bass']:.2f})"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, stems={**a.stems, "bass": 0.0})
        result.append(a)
    return result


def _inject_eq_duration(actions: list[MixAction]) -> list[MixAction]:
    """Any eq action missing eq_duration_bars gets the default ramp of 4 bars."""
    result = []
    for a in actions:
        if a.type == "eq" and not a.eq_duration_bars:
            msg = f"injected eq_duration_bars=4 on eq({a.track} bar={a.bar})"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, eq_duration_bars=4)
        result.append(a)
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


def _align_crossfade_starts(actions: list[MixAction]) -> list[MixAction]:
    """
    fade_out.start_bar must not precede fade_in.start_bar — a gap where T1 is fading
    but T2 hasn't started creates silence. Snap fade_out.start_bar forward to match
    fade_in.start_bar when it's more than 4 bars early.

    Only snaps when the fade_out and fade_in windows actually overlap in time — prevents
    incorrectly pairing transitions from different parts of a 3+ track set.
    """
    fade_ins = [a for a in actions if a.type == "fade_in"]
    result = []
    for a in actions:
        if a.type == "fade_out" and a.start_bar is not None:
            fo_end = a.start_bar + (a.duration_bars or DURATION_PREFERRED_MIN)
            for fi in fade_ins:
                if fi.track == a.track or fi.start_bar is None:
                    continue
                fi_end = fi.start_bar + (fi.duration_bars or DURATION_PREFERRED_MIN)
                if fi.start_bar < fo_end and a.start_bar < fi_end:
                    if a.start_bar < fi.start_bar - 4:
                        msg = (
                            f"snapped fade_out({a.track}) start_bar {a.start_bar}→{fi.start_bar} "
                            f"(was {fi.start_bar - a.start_bar} bars before fade_in)"
                        )
                        logger.debug("NORMALIZER FIX: %s", msg)
                        print(f"[normalizer] {msg}")
                        a = dataclasses.replace(a, start_bar=fi.start_bar)
                    break
        result.append(a)
    return result


def _fix_play_from_bar_after_fade_in(actions: list[MixAction]) -> list[MixAction]:
    """
    For every play that immediately follows a fade_in on the same track, enforce:
        play.at_bar   == fade_in.start_bar + fade_in.duration_bars
        play.from_bar == fade_in.from_bar  + fade_in.duration_bars

    Claude frequently emits from_bar=0 on the play (causing the first duration_bars of
    the track to play again), or places the play at the wrong at_bar. This pass corrects
    both fields. 'Immediately follows' means the play is the earliest play at or after
    the fade_in end bar for that track.
    """
    result = list(actions)
    for fi in actions:
        if fi.type != "fade_in":
            continue
        fade_end_bar    = (fi.start_bar or 0) + (fi.duration_bars or 0)
        correct_from    = (fi.from_bar  or 0) + (fi.duration_bars or 0)
        # Find the first play for this track at or after the fade START (not fade end) so we
        # also catch plays that Claude placed at the pre-clamp fade end (which may now fall
        # inside the window after normalizer clamped duration_bars up to 16).
        following_plays = [
            (i, a) for i, a in enumerate(result)
            if a.type == "play" and a.track == fi.track and (a.at_bar or 0) >= (fi.start_bar or 0)
        ]
        if not following_plays:
            continue
        idx, play = min(following_plays, key=lambda x: x[1].at_bar or 0)
        needs_fix = (play.at_bar != fade_end_bar) or (play.from_bar != correct_from)
        if needs_fix:
            msg = (
                f"corrected play for {fi.track}: "
                f"at_bar {play.at_bar}→{fade_end_bar}, from_bar {play.from_bar}→{correct_from}"
            )
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            result[idx] = dataclasses.replace(play, at_bar=fade_end_bar, from_bar=correct_from)
    return result


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
            msg = (
                f"injected implied play for {fi.track} at bar {fade_end_bar} "
                f"(from_bar={from_bar}) — no play followed its fade_in"
            )
            logger.debug("NORMALIZER INJECT: %s", msg)
            print(f"[normalizer] {msg}")
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
        msg = (
            f"auto-injected fade_out for {tid} at bar {fade_start} "
            f"(anchored on {anchor.type}@{anchor_bar}) — was missing"
        )
        logger.debug("NORMALIZER INJECT: %s", msg)
        print(f"[normalizer] {msg}")

    if not injected:
        return actions
    return sorted(actions + injected, key=_action_sort_key)


def _restore_incoming_eq(actions: list[MixAction]) -> list[MixAction]:
    """
    EQ is persistent (from bar → end of track). Correct for outgoing tracks (fading
    out). Destructive for continuing tracks: any suppression during the overlap window
    persists for the rest of the mix.

    A "continuing" track is one that has a play or fade_in (it enters the mix) but no
    fade_out (it doesn't exit). For every non-unity eq on such a track, inject a restore
    eq(low=1.0, mid=1.0, high=1.0) at the end of the transition window.

    The transition end is determined by:
      - fade_in end (start_bar + duration_bars) if the track has a fade_in, or
      - the play at_bar + PHRASE (one phrase after entry) if no fade_in.
    """
    incoming_tids = {
        a.track for a in actions if a.type in ("fade_in", "play")
    }
    outgoing_tids = {
        a.track for a in actions if a.type == "fade_out"
    }
    # Tracks that continue past the transition window (no fade_out).
    continuing_tids = incoming_tids - outgoing_tids

    # Do NOT restore mid/high EQ on outgoing tracks. When the agent sets eq(T1, mid=0.3)
    # before the fade_out, that is an intentional vocal/harmonic duck to make space for T2.
    # Restoring it at fade_out start would undo the ducking right as T1 begins its fade —
    # audibly wrong (T1 comes back to full mid for 8 bars then fades out).
    outgoing_eq_restore: dict[str, int] = {}  # intentionally left empty

    def _transition_end_bar(tid: str) -> int:
        """Bar at which the blend window for this incoming track closes."""
        fi = next((x for x in actions if x.type == "fade_in" and x.track == tid), None)
        if fi is not None:
            return (fi.start_bar or 0) + (fi.duration_bars or 0)
        # No fade_in: find the earliest play for this track and use +PHRASE
        plays = [x for x in actions if x.type == "play" and x.track == tid]
        if plays:
            earliest = min(plays, key=lambda x: x.at_bar or 0)
            return (earliest.at_bar or 0) + PHRASE
        return PHRASE  # fallback

    injected: list[MixAction] = []

    # Restore EQ on outgoing tracks that have mid/high cut before their fade_out
    for tid, restore_bar in outgoing_eq_restore.items():
        already = any(
            x.type == "eq" and x.track == tid
            and (x.bar or 0) >= restore_bar
            and x.mid == 1.0 and x.high == 1.0
            for x in actions
        )
        if not already:
            injected.append(MixAction(
                type="eq", track=tid, bar=restore_bar,
                low=1.0, mid=1.0, high=1.0,
            ))
            msg = f"restored mid/high EQ for outgoing {tid} at bar {restore_bar} (fade_out start)"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")

    for a in actions:
        if a.type != "eq" or a.track not in continuing_tids:
            continue
        eq_any_non_default = (
            (a.low  is not None and a.low  != 1.0) or
            (a.mid  is not None and a.mid  != 1.0) or
            (a.high is not None and a.high != 1.0)
        )
        if not eq_any_non_default:
            continue
        restore_bar = round(_transition_end_bar(a.track) / PHRASE) * PHRASE
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
            msg = (
                f"restored EQ for continuing {a.track} at bar {restore_bar} "
                f"(had low={a.low} mid={a.mid} high={a.high} from bar {a.bar})"
            )
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")

    if not injected:
        return actions
    return sorted(actions + injected, key=_action_sort_key)


def _snap_bass_swap_bars(actions: list[MixAction]) -> list[MixAction]:
    """
    Snap every bass_swap.at_bar to a phrase-aligned position inside the fade window.

    Simple nearest-multiple-of-8 rounding can land the swap at the very start of the
    blend (e.g. round(52/8)*8 = 48 via banker's rounding when fade starts at 48).
    That creates a full-window bass strip.  Instead: when the naive snap would land at
    or before the fade_in start, recalculate to the phrase-aligned midpoint of the
    fade window so the swap fires in the second half of the blend.
    """
    # Pre-compute each incoming track's fade window so we can avoid the start edge.
    fade_windows: dict[str, tuple[int, int]] = {}
    for a in actions:
        if a.type == "fade_in":
            fi_start = a.start_bar or 0
            fi_end   = fi_start + (a.duration_bars or DURATION_PREFERRED_MIN)
            fade_windows[a.track] = (fi_start, fi_end)

    # Pass 1: snap bass_swaps, record (incoming_track, old_bar) -> snapped_bar for any moves
    snap_map: dict[tuple[str, int], int] = {}
    result = []
    for a in actions:
        if a.type == "bass_swap" and a.at_bar is not None:
            snapped = round(a.at_bar / PHRASE) * PHRASE

            # Guard: don't land at or before the fade_in start (no-bass for the whole blend).
            if a.incoming_track in fade_windows:
                fi_start, fi_end = fade_windows[a.incoming_track]
                if snapped <= fi_start and fi_end > fi_start + PHRASE:
                    mid        = fi_start + (fi_end - fi_start) // 2
                    mid_phrase = (mid // PHRASE) * PHRASE
                    snapped    = max(fi_start + PHRASE, min(mid_phrase, fi_end - PHRASE))

            if snapped != a.at_bar:
                msg = f"snapped bass_swap({a.track}) at_bar {a.at_bar}→{snapped} (phrase alignment)"
                logger.debug("NORMALIZER FIX: %s", msg)
                print(f"[normalizer] {msg}")
                if a.incoming_track:
                    snap_map[(a.incoming_track, a.at_bar)] = snapped
                a = dataclasses.replace(a, at_bar=snapped)
        result.append(a)

    if not snap_map:
        return result

    # Pass 2: co-snap any eq(incoming_track, bar=old_bar, low=1.0) restore paired with the swap
    final = []
    for a in result:
        if (
            a.type == "eq"
            and a.bar is not None
            and a.low == 1.0
            and (a.track, a.bar) in snap_map
        ):
            snapped_bar = snap_map[(a.track, a.bar)]
            msg = f"co-snapped eq({a.track}) bar {a.bar}→{snapped_bar} (bass_swap restore alignment)"
            logger.debug("NORMALIZER FIX: %s", msg)
            print(f"[normalizer] {msg}")
            a = dataclasses.replace(a, bar=snapped_bar)
        final.append(a)

    return final


def _snap_fade_in_anchor(actions: list[MixAction]) -> list[MixAction]:
    """
    Snap each fade_in.start_bar to the nearest ×PHRASE boundary.
    Co-shift all subsequent actions on the same track AND any bass_swap
    within a 40-bar window by the same delta, so relative offsets are preserved.

    Must run before _snap_bass_swap_bars to prevent independent snapping
    from creating a zero-gap between fade_in and bass_swap.
    """
    result = list(actions)

    for fi in [a for a in actions if a.type == "fade_in" and a.start_bar is not None]:
        orig    = fi.start_bar
        snapped = round(orig / PHRASE) * PHRASE
        delta   = snapped - orig
        if delta == 0:
            continue

        tid = fi.track
        msg = f"anchor-snapped fade_in({tid}) start_bar {orig}→{snapped} (Δ{delta:+d})"
        logger.debug("NORMALIZER FIX: %s", msg)
        print(f"[normalizer] {msg}")

        new_result = []
        for a in result:
            if a.track == tid:
                if a.type == "fade_in" and a.start_bar == orig:
                    a = dataclasses.replace(a, start_bar=snapped)
                elif a.start_bar is not None and a.start_bar > orig:
                    a = dataclasses.replace(a, start_bar=a.start_bar + delta)
                elif a.at_bar is not None and a.at_bar > orig:
                    a = dataclasses.replace(a, at_bar=a.at_bar + delta)
                elif a.bar is not None and a.bar > orig:
                    a = dataclasses.replace(a, bar=a.bar + delta)
            elif a.type == "bass_swap" and a.at_bar is not None and orig <= a.at_bar <= orig + 40:
                a = dataclasses.replace(a, at_bar=a.at_bar + delta)
            new_result.append(a)
        result = new_result

    return result


def _ramp_stems_release(actions: list[MixAction]) -> list[MixAction]:
    """
    When fade_in has suppressed vocals (stems.vocals < 0.3), inject a mid EQ dip
    in the 4 bars before fade-end and a matching bloom at fade-end. This prevents
    vocals slamming in at full volume the instant stems constraints lift.

    Dip  (bar = fade_end-4): ramps mid→0.0 over 4 bars (mids silent as fade ends)
    Bloom (bar = fade_end):  ramps mid→1.0 over 4 bars (vocals swell in naturally)
    """
    RAMP = 4
    injected: list[MixAction] = []

    for fi in [a for a in actions if a.type == "fade_in" and a.stems]:
        if fi.stems.get("vocals", 1.0) >= 0.3:
            continue

        fade_end = (fi.start_bar or 0) + (fi.duration_bars or 0)
        tid = fi.track

        # Don't inject if Claude already placed an EQ mid-action near the handoff
        already = any(
            a.type == "eq" and a.track == tid
            and a.mid is not None
            and (a.bar or 0) >= fade_end - RAMP
            for a in actions
        )
        if already:
            continue

        ramp_start = fade_end - RAMP
        msg = f"stems-release EQ ramp for {tid}: mid dip bar {ramp_start}, bloom bar {fade_end}"
        logger.debug("NORMALIZER INJECT: %s", msg)
        print(f"[normalizer] {msg}")

        # Dip: mid arrives at 0.0 and low stays 0.0 so the bloom's eq_from.low=0.0,
        # giving a smooth 0→1 bass ramp (instead of a slam) when the full track takes over.
        has_bass_suppressed = fi.stems.get("bass", 1.0) == 0.0 if fi.stems else False
        dip_low = 0.0 if has_bass_suppressed else 1.0
        injected.append(MixAction(
            type="eq", track=tid, bar=ramp_start,
            low=dip_low, mid=0.0, high=0.7, eq_duration_bars=RAMP,
        ))
        # Bloom: mid and high swell back to unity — vocals come in naturally
        injected.append(MixAction(
            type="eq", track=tid, bar=fade_end,
            low=1.0, mid=1.0, high=1.0, eq_duration_bars=RAMP,
        ))

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
