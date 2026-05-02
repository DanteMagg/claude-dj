from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Optional

from schema import BarGrid, CuePoint, KeyInfo, StemPaths, TrackAnalysis
from state import LibraryEntry


class Library:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._file = self._cache_dir / "library.json"
        self._entries: dict[str, LibraryEntry] = {}

    def load(self) -> None:
        if not self._file.exists():
            self._entries = {}
            return
        try:
            raw: dict[str, dict] = json.loads(self._file.read_text())
            self._entries = {}
            for h, v in raw.items():
                v.setdefault("loudness_dbfs", -14.0)
                self._entries[h] = LibraryEntry(**v)
        except Exception:
            self._entries = {}

    def save(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".json.tmp")
        data = {h: dataclasses.asdict(e) for h, e in self._entries.items()}
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(str(tmp), str(self._file))

    def get(self, hash: str) -> Optional[LibraryEntry]:
        return self._entries.get(hash)

    def get_all(self) -> list[LibraryEntry]:
        return sorted(
            self._entries.values(),
            key=lambda e: (e.artist.lower(), e.title.lower()),
        )

    def upsert(self, hash: str, entry: LibraryEntry) -> None:
        self._entries[hash] = entry
        self.save()

    def resolve(self, val: str) -> Optional[str]:
        if val in self._entries:
            return val
        for h, e in self._entries.items():
            if e.path == val:
                return h
        return None

    def to_analysis(self, hash: str, track_id: str) -> TrackAnalysis:
        e = self._entries[hash]
        key_std = e.key_standard
        parts = key_std.split()
        tonic = parts[0] if parts else "C"
        mode = "minor" if key_std.endswith("m") or "minor" in key_std else "major"
        bpm = float(e.bpm)
        dur = float(e.duration_s)
        n_bars = max(1, int(dur * bpm / 240))
        return TrackAnalysis(
            id=track_id,
            title=e.title,
            artist=e.artist,
            file=e.path,
            duration_s=dur,
            bpm=bpm,
            first_downbeat_s=float(e.first_downbeat_s),
            key=KeyInfo(
                camelot=e.key_camelot,
                standard=key_std,
                mode=mode,
                tonic=tonic,
            ),
            energy_overall=int(e.energy),
            loudness_dbfs=float(e.loudness_dbfs),
            bar_grid=BarGrid(n_bars=n_bars, beats_per_bar=4),
            energy_curve_per_bar=e.energy_curve,
            sections=[],
            cue_points=[
                CuePoint(name=c["name"], bar=c["bar"], type=c.get("type", "phrase_start"))
                for c in e.cue_points
            ],
            stems=StemPaths(vocals="", drums="", bass="", other=""),
        )
