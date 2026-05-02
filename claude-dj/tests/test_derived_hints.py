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
