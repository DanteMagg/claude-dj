# claude-dj/state.py
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class LibraryEntry:
    hash: str
    path: str
    title: str
    artist: str
    bpm: float
    key_camelot: str
    key_standard: str
    energy: int
    duration_s: float
    energy_curve: str
    cue_points: list[dict]
    first_downbeat_s: float
    analyzed_at: str
    loudness_dbfs: float = -14.0


@dataclass
class ScanJob:
    scan_id: str
    status: Literal["running", "done", "error"]
    progress: int = 0
    total: int = 0
    known: int = 0
    new: int = 0
    skipped: int = 0
    error: Optional[str] = None


@dataclass
class DjDeckA:
    track_id: str
    hash: str
    title: str
    start_bar: int
    status: str = "playing"


@dataclass
class DjDeckB:
    status: Literal["starting", "analyzing", "selecting", "planning", "loading", "ready"]
    title: str
    hash: Optional[str] = None   # set once the track's hash is known (after analyze)


@dataclass
class TransitionLogEntry:
    """One planned transition, stored for post-hoc inspection."""
    ts:           str            # ISO timestamp when planning completed
    from_id:      str            # e.g. "T1"
    to_id:        str            # e.g. "T2"
    from_title:   str
    to_title:     str
    offset_bar:   int            # global bar where T2 starts playing
    reasoning:    str            # Claude's reasoning text for this transition
    actions:      list[dict]     # serialised MixAction list (from sub_script)


@dataclass
class DjSessionState:
    dj_id: str
    status: Literal["starting", "playing", "stopped", "error"]
    model: str
    let_claude_pick: bool
    pool: list[str]
    queue: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    deck_a: Optional[DjDeckA] = None
    deck_b: Optional[DjDeckB] = None
    track_counter: int = 0
    current_start_bar: int = 0
    ref_bpm: Optional[float] = None
    error: Optional[str] = None
    transition_log: list = field(default_factory=list)  # list[TransitionLogEntry]


@dataclass
class AudioSession:
    session_id: str
    status: Literal["loading", "ready", "error"]
    script: object          # MixScript — typed as object to avoid circular import
    ref_bpm: float
    tracks: list[dict]
    load_progress: int = 0
    load_total: int = 0
    scheduler: Optional[object] = None   # ChunkScheduler
    error: Optional[str] = None


class ScanJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}

    def create(self, scan_id: str) -> ScanJob:
        job = ScanJob(scan_id=scan_id, status="running")
        self._jobs[scan_id] = job
        return job

    def get(self, scan_id: str) -> Optional[ScanJob]:
        return self._jobs.get(scan_id)


class AudioSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AudioSession] = {}

    def create(self, session_id: str, sess: AudioSession) -> None:
        self._sessions[session_id] = sess

    def get(self, session_id: str) -> Optional[AudioSession]:
        return self._sessions.get(session_id)

    def values(self):
        return self._sessions.values()


class DjSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, DjSessionState] = {}

    def create(self, dj_id: str, state: DjSessionState) -> None:
        self._sessions[dj_id] = state

    def get(self, dj_id: str) -> Optional[DjSessionState]:
        return self._sessions.get(dj_id)
