from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KeyInfo:
    camelot: str
    standard: str
    mode: str
    tonic: str


@dataclass
class StemPresence:
    presence: int  # 0-10
    rms_db: float


@dataclass
class SectionStems:
    drums: StemPresence
    bass: StemPresence
    vocals: StemPresence
    other: StemPresence


@dataclass
class Section:
    label: str
    start_bar: int
    end_bar: int
    start_s: float
    end_s: float
    energy: int  # 0-10
    loudness_dbfs: float
    stems: SectionStems


@dataclass
class CuePoint:
    name: str
    bar: int
    type: str  # phrase_start | outro_start | drop_start


@dataclass
class BarGrid:
    n_bars: int
    beats_per_bar: int = 4


@dataclass
class StemPaths:
    vocals: str
    drums: str
    bass: str
    other: str


@dataclass
class TrackAnalysis:
    id: str
    title: str
    artist: str
    file: str
    duration_s: float
    bpm: float
    first_downbeat_s: float
    key: KeyInfo
    energy_overall: int
    loudness_lufs: float
    bar_grid: BarGrid
    energy_curve_per_bar: str
    sections: list[Section]
    cue_points: list[CuePoint]
    stems: StemPaths

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# --- Mix script types ---

@dataclass
class MixTrackRef:
    id: str
    path: str
    bpm: float
    first_downbeat_s: float


@dataclass
class MixAction:
    type: str  # play | fade_in | fade_out | eq
    track: str
    # play
    at_bar: Optional[int] = None
    from_bar: Optional[int] = None
    # fade
    start_bar: Optional[int] = None
    duration_bars: Optional[int] = None
    stems: Optional[dict[str, float]] = None
    # eq
    bar: Optional[int] = None
    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None


@dataclass
class MixScript:
    mix_title: str
    reasoning: str
    tracks: list[MixTrackRef]
    actions: list[MixAction]
