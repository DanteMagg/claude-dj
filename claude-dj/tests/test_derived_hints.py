# claude-dj/tests/test_derived_hints.py
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mix_director import _format_zone_table


def _row(bar, drums, harmonic, rms, brightness=0.40, onsets=2, vocals=0.0, tags=None):
    return {
        "bar": bar, "drums": drums, "harmonic": harmonic, "rms": rms,
        "brightness": brightness, "onsets": onsets,
        "vocals": vocals, "tags": tags or [],
    }


# ── _format_zone_table ──────────────────────────────────────────────────────

def test_zone_table_includes_vocals_column():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.08)]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "vox=0.08" in table


def test_zone_table_includes_tags():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.05, tags=["LOOP_SAFE"])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "[LOOP_SAFE]" in table


def test_zone_table_multiple_tags():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.50, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "[VOCAL_ACTIVE]" in table
    assert "[LOOP_UNSAFE_VOX]" in table


def test_zone_table_no_tags_row_clean():
    rows = [_row(80, 0.70, 0.05, 0.40, vocals=0.05, tags=[])]
    table = _format_zone_table(rows, "T1", "exit zone")
    assert "vox=0.05" in table
    # No tag brackets should appear for this row
    assert "[" not in table or "exit zone" not in table.split("[")[0]


# --- Task 7 additions ---

from mix_director import _compute_zone_hints


def _make_zone(start_bar, n, drums=0.70, harmonic=0.05, rms=0.40, vocals=0.0, tags=None):
    rows = []
    for i in range(n):
        t = list(tags) if tags else []
        rows.append({
            "bar": start_bar + i, "drums": drums, "harmonic": harmonic,
            "rms": rms, "brightness": 0.4, "onsets": 2,
            "vocals": vocals, "tags": t,
        })
    return rows


# ── _compute_zone_hints (no profiles) ───────────────────────────────────────

def test_hints_returns_nonempty_string_for_zones():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert isinstance(result, str)
    assert len(result) > 0


def test_bass_swap_hint_present():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "bass_swap" in result.lower() or "preferred" in result.lower()


def test_bass_swap_has_because_clause():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "BECAUSE" in result


# ── _compute_zone_hints (with VOCAL_ACTIVE tags) ─────────────────────────────

def test_vocal_situation_block_present_when_vocals_in_t1():
    t1 = _make_zone(64, 16, vocals=0.50, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "VOCAL SITUATION" in result


def test_vocal_situation_shows_t1_last_vocal_bar():
    t1_zone = []
    for i in range(8):
        t1_zone.append({"bar": 64 + i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.5,
                        "tags": ["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"]})
    for i in range(8):
        t1_zone.append({"bar": 72 + i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.05,
                        "tags": ["LOOP_SAFE"]})
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1_zone, t2)
    assert "bar 71" in result or "b71" in result  # last vocal bar (0-indexed: 64+7=71)


def test_vocal_situation_shows_t2_vocal_entry():
    t1 = _make_zone(64, 16)
    t2_zone = []
    for i in range(4):
        t2_zone.append({"bar": i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.05, "tags": []})
    for i in range(4, 16):
        t2_zone.append({"bar": i, "drums": 0.7, "harmonic": 0.05, "rms": 0.4,
                        "brightness": 0.4, "onsets": 2, "vocals": 0.50,
                        "tags": ["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"]})
    result = _compute_zone_hints(t1, t2_zone)
    assert "bar 4" in result or "b4" in result  # first T2 vocal bar


# ── Loop candidates block ────────────────────────────────────────────────────

def test_loop_candidates_block_present_when_loop_safe_bars():
    t1 = _make_zone(64, 16, tags=["LOOP_SAFE"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "LOOP CANDIDATES" in result


def test_loop_candidates_block_shows_unsafe():
    t1 = _make_zone(64, 16, vocals=0.5, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "LOOP_UNSAFE" in result or "LOOP CANDIDATES" in result


# ── Technique recommendation ─────────────────────────────────────────────────

def test_technique_recommendation_block_present():
    t1 = _make_zone(64, 16)
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "RECOMMENDED TECHNIQUE" in result


def test_technique_recommendation_has_avoid_clause():
    t1 = _make_zone(64, 16, vocals=0.5, tags=["VOCAL_ACTIVE", "LOOP_UNSAFE_VOX"])
    t2 = _make_zone(0, 16)
    result = _compute_zone_hints(t1, t2)
    assert "AVOID" in result


# ── Phase 1 profile injection ────────────────────────────────────────────────

from mix_director import _format_profiles_section


def test_profiles_section_empty_when_no_profiles():
    result = _format_profiles_section(None, None)
    assert result == ""


def test_profiles_section_shows_t1_outro():
    from schema import LoopCandidate, MixingProfile, TransitionWindow
    p1 = MixingProfile(
        vocal_bars=[[16, 48]],
        loop_candidates=[LoopCandidate(start_bar=80, bars=8, reason="clean")],
        transition_windows=[TransitionWindow(bar=96, quality=9, character="drums-only")],
        intro_type="melodic",
        outro_type="drums-only",
        dj_notes="Clean outro from bar 96.",
    )
    result = _format_profiles_section(p1, None)
    assert "T1 MIXING PROFILE" in result
    assert "outro: drums-only" in result
    assert "bar 96" in result


def test_profiles_section_shows_t2_intro():
    from schema import MixingProfile
    p2 = MixingProfile(
        vocal_bars=[],
        loop_candidates=[],
        transition_windows=[],
        intro_type="drums-only",
        outro_type="fade-silence",
        dj_notes="Drums-only intro.",
    )
    result = _format_profiles_section(None, p2)
    assert "T2 MIXING PROFILE" in result
    assert "intro: drums-only" in result
