from datetime import datetime
from pathlib import Path

import pytest

from state import LibraryEntry
from library import Library


def _entry(hash="abc123", path="/music/t.mp3", title="Test", artist="Artist") -> LibraryEntry:
    return LibraryEntry(
        hash=hash, path=path, title=title, artist=artist,
        bpm=128.0, key_camelot="8B", key_standard="C major",
        energy=7, duration_s=300.0, energy_curve="56789",
        cue_points=[{"name": "drop", "bar": 32, "type": "phrase_start"}],
        first_downbeat_s=0.5, analyzed_at=datetime.utcnow().isoformat(),
        loudness_dbfs=-14.0,
    )


def test_load_on_missing_file_starts_empty(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    assert lib.get_all() == []


def test_upsert_then_get_returns_entry(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    e = _entry()
    lib.upsert("abc123", e)
    assert lib.get("abc123") == e


def test_save_and_reload_preserves_all_fields(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())

    lib2 = Library(tmp_path)
    lib2.load()
    loaded = lib2.get("abc123")
    assert loaded is not None
    assert loaded.title == "Test"
    assert loaded.bpm == 128.0
    assert loaded.cue_points == [{"name": "drop", "bar": 32, "type": "phrase_start"}]
    assert loaded.loudness_dbfs == -14.0


def test_resolve_by_hash(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    assert lib.resolve("abc123") == "abc123"


def test_resolve_by_path(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry(path="/music/t.mp3"))
    assert lib.resolve("/music/t.mp3") == "abc123"


def test_resolve_nonexistent_returns_none(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    assert lib.resolve("nonexistent") is None


def test_atomic_save_leaves_no_tmp_file(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    assert not (tmp_path / "library.json.tmp").exists()
    assert (tmp_path / "library.json").exists()


def test_get_all_sorted_by_artist_then_title(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("h1", _entry("h1", title="Zeal", artist="Beta"))
    lib.upsert("h2", _entry("h2", title="Alpha", artist="Alpha"))
    lib.upsert("h3", _entry("h3", title="Bravo", artist="Alpha"))
    result = lib.get_all()
    assert [e.hash for e in result] == ["h2", "h3", "h1"]


def test_to_analysis_builds_track_analysis(tmp_path):
    lib = Library(tmp_path)
    lib.load()
    lib.upsert("abc123", _entry())
    analysis = lib.to_analysis("abc123", "T1")
    assert analysis.id == "T1"
    assert analysis.title == "Test"
    assert analysis.bpm == 128.0
    assert analysis.key.camelot == "8B"
    assert analysis.loudness_dbfs == -14.0
