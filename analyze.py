"""
Audio analysis pipeline. Uses librosa for all analysis (beat tracking, key,
segmentation, energy). Demucs for stem separation.

No allin1/madmom dependency — both are incompatible with numpy 2.x / scipy 1.x
without substantial patching. Segmentation uses librosa spectral clustering.
Sections will have auto-labeled boundaries (A/B/C/...) rather than named
sections (intro/drop/outro); Claude can reason about their character from the
energy and stem data.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
from pydub import AudioSegment

from schema import (
    BarGrid, CuePoint, KeyInfo, Section, SectionStems, StemPresence,
    StemPaths, TrackAnalysis,
)

CACHE_DIR = Path(__file__).parent / "cache"
SILENCE_THRESHOLD_DB = -30.0
BEATS_PER_BAR = 4


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def track_cache_dir(path: str) -> Path:
    h = file_hash(path)
    d = CACHE_DIR / h
    d.mkdir(parents=True, exist_ok=True)
    return d


def separate_stems(audio_path: str, cache_dir: Path) -> StemPaths:
    stems_dir = cache_dir / "stems"
    expected = {
        "vocals": stems_dir / "vocals.wav",
        "drums": stems_dir / "drums.wav",
        "bass": stems_dir / "bass.wav",
        "other": stems_dir / "other.wav",
    }
    if all(p.exists() for p in expected.values()):
        return StemPaths(**{k: str(v) for k, v in expected.items()})

    stems_dir.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            sys.executable, "-m", "demucs",
            "-n", "htdemucs",
            "-o", str(stems_dir),
            audio_path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed:\n{result.stderr}")

    track_stem = Path(audio_path).stem
    demucs_out = stems_dir / "htdemucs" / track_stem
    if not demucs_out.exists():
        raise RuntimeError(f"Demucs output not found at {demucs_out}")

    for stem_name, dest in expected.items():
        src = demucs_out / f"{stem_name}.wav"
        src.rename(dest)

    return StemPaths(**{k: str(v) for k, v in expected.items()})


def estimate_key(y: np.ndarray, sr: int) -> KeyInfo:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    tonic_idx = int(np.argmax(chroma_mean))

    # Krumhansl-Schmuckler profiles
    major_profile = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    minor_profile = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

    note_names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    camelot_major = ["8B","3B","10B","5B","12B","7B","2B","9B","4B","11B","6B","1B"]
    camelot_minor = ["5A","12A","7A","2A","9A","4A","11A","6A","1A","8A","3A","10A"]

    best_score = -np.inf
    best_tonic = 0
    best_mode = "major"

    for i in range(12):
        rolled_chroma = np.roll(chroma_mean, -i)
        major_score = np.corrcoef(rolled_chroma, major_profile)[0, 1]
        minor_score = np.corrcoef(rolled_chroma, minor_profile)[0, 1]
        if major_score > best_score:
            best_score = major_score
            best_tonic = i
            best_mode = "major"
        if minor_score > best_score:
            best_score = minor_score
            best_tonic = i
            best_mode = "minor"

    tonic_name = note_names[best_tonic]
    if best_mode == "major":
        standard = f"{tonic_name} major"
        camelot = camelot_major[best_tonic]
    else:
        standard = f"{tonic_name}m"
        camelot = camelot_minor[best_tonic]

    return KeyInfo(camelot=camelot, standard=standard, mode=best_mode, tonic=tonic_name)


def compute_rms_db(y: np.ndarray) -> float:
    rms = np.sqrt(np.mean(y ** 2))
    if rms < 1e-10:
        return -80.0
    return float(20 * np.log10(rms))


def presence_from_rms(rms_db: float, max_rms_db: float) -> int:
    if not np.isfinite(rms_db) or rms_db < SILENCE_THRESHOLD_DB:
        return 0
    denom = max_rms_db - SILENCE_THRESHOLD_DB
    if not np.isfinite(max_rms_db) or denom <= 0:
        return 0
    normalized = (rms_db - SILENCE_THRESHOLD_DB) / denom
    return max(0, min(10, int(normalized * 10)))


def segment_audio(y: np.ndarray, sr: int, downbeats: np.ndarray, n_segments: int = 6) -> list[tuple[float, float]]:
    """Spectral-clustering-based segmentation. Returns list of (start_s, end_s)."""
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=12)
        R = librosa.segment.recurrence_matrix(mfcc, mode="affinity", sym=True)
        bounds_frames = librosa.segment.agglomerative(R, k=min(n_segments, len(downbeats) - 1))
        bounds_times = librosa.frames_to_time(bounds_frames, sr=sr)
        bounds_times = np.concatenate([[0.0], bounds_times, [librosa.get_duration(y=y, sr=sr)]])
        return [(float(bounds_times[i]), float(bounds_times[i + 1])) for i in range(len(bounds_times) - 1)]
    except Exception:
        # fallback: split evenly on downbeats
        duration = librosa.get_duration(y=y, sr=sr)
        step = max(1, len(downbeats) // n_segments)
        boundaries = [float(downbeats[i]) for i in range(0, len(downbeats), step)]
        boundaries.append(duration)
        return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def time_to_bar(t: float, downbeats: np.ndarray) -> int:
    idx = np.searchsorted(downbeats, t, side="right") - 1
    return max(0, int(idx))


ABSENT_STEM = StemPresence(presence=0, rms_db=-80.0)
ABSENT_STEMS = SectionStems(
    drums=ABSENT_STEM, bass=ABSENT_STEM, vocals=ABSENT_STEM, other=ABSENT_STEM
)


def build_sections(
    y: np.ndarray,
    sr: int,
    downbeats: np.ndarray,
    stem_paths: Optional[StemPaths],
) -> list[Section]:
    segments = segment_audio(y, sr, downbeats)
    labels = [chr(ord("A") + i) for i in range(len(segments))]

    # load stems once (skip if --no-stems)
    stem_arrays: dict[str, np.ndarray] = {}
    stem_srs: dict[str, int] = {}
    stem_max_rms: dict[str, float] = {}
    if stem_paths is not None:
        for stem_name in ("vocals", "drums", "bass", "other"):
            path = getattr(stem_paths, stem_name)
            s_y, s_sr = librosa.load(path, sr=None, mono=True)
            stem_arrays[stem_name] = s_y
            stem_srs[stem_name] = s_sr
            stem_max_rms[stem_name] = compute_rms_db(s_y)

    sections: list[Section] = []
    for label, (start_s, end_s) in zip(labels, segments):
        start_bar = time_to_bar(start_s, downbeats)
        end_bar = time_to_bar(end_s, downbeats)

        start_sample = librosa.time_to_samples(start_s, sr=sr)
        end_sample = librosa.time_to_samples(end_s, sr=sr)
        y_seg = y[start_sample:end_sample]
        mix_rms_db = compute_rms_db(y_seg)
        if np.isnan(mix_rms_db):
            mix_rms_db = -80.0
        energy = max(0, min(10, int((mix_rms_db + 40) / 4)))

        if stem_arrays:
            stem_presences: dict[str, StemPresence] = {}
            for stem_name, s_y in stem_arrays.items():
                s_sr = stem_srs[stem_name]
                s_start = librosa.time_to_samples(start_s, sr=s_sr)
                s_end = librosa.time_to_samples(end_s, sr=s_sr)
                seg = s_y[s_start:s_end]
                rms = compute_rms_db(seg)
                pres = presence_from_rms(rms, stem_max_rms[stem_name])
                stem_presences[stem_name] = StemPresence(presence=pres, rms_db=round(rms, 1))
            section_stems = SectionStems(**stem_presences)
        else:
            section_stems = ABSENT_STEMS

        # relabel as "drop" if high energy + drums (works even without stems via energy alone)
        if energy >= 8 and (not stem_arrays or section_stems.drums.presence >= 8):
            label = "drop"

        sections.append(Section(
            label=label,
            start_bar=start_bar,
            end_bar=end_bar,
            start_s=round(start_s, 2),
            end_s=round(end_s, 2),
            energy=energy,
            loudness_dbfs=round(mix_rms_db, 1),
            stems=section_stems,
        ))

    return sections


def _energy_cue_points(energy_curve: list[int], n_bars: int) -> list[CuePoint]:
    phrase = 8
    n = len(energy_curve)
    if n == 0:
        return [
            CuePoint(name="mix_in",  bar=0,                      type="phrase_start"),
            CuePoint(name="mix_out", bar=max(0, n_bars - phrase), type="outro_start"),
        ]

    mean_e = sum(energy_curve) / n

    # mix_in: first phrase boundary after energy sustains >= mean for 4+ bars
    mix_in = 0
    for i in range(n - 3):
        if all(e >= mean_e for e in energy_curve[i:i + 4]):
            mix_in = (i // phrase) * phrase
            break

    # mix_out: scan backward from the end, but only in the second half of the track.
    # This forces mix_out toward the outro rather than mid-track breakdowns, producing
    # longer, more complete plays per track in the mix.
    half = n // 2
    mix_out = max(0, ((n - 1) // phrase) * phrase)
    for i in range(n - 4, max(half, 0), -1):
        if all(e >= mean_e for e in energy_curve[i:i + 4]):
            mix_out = min(n_bars - 1, ((i + 4 + phrase - 1) // phrase) * phrase)
            break

    return [
        CuePoint(name="mix_in",  bar=mix_in,  type="phrase_start"),
        CuePoint(name="mix_out", bar=mix_out, type="outro_start"),
    ]


def analyze_track(audio_path: str, track_id: str) -> TrackAnalysis:
    audio_path = str(Path(audio_path).resolve())
    cache_dir = track_cache_dir(audio_path)
    analysis_cache = cache_dir / "analysis.json"

    if analysis_cache.exists():
        with open(analysis_cache) as f:
            d = json.load(f)
        return _dict_to_analysis(d)

    print(f"  [analyze] loading {Path(audio_path).name}")
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    # Beat + downbeat tracking
    print("  [analyze] beat tracking")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Downbeat phase correction: try all 4 offsets, pick the one where downbeats
    # land on strongest onsets (beat 1 of each bar has the strongest transient on
    # average, e.g. kick drum + chord hit).
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
    best_phase, best_score = 0, -np.inf
    for phase in range(BEATS_PER_BAR):
        candidate = beat_times[phase::BEATS_PER_BAR]
        idxs = np.searchsorted(onset_times, candidate).clip(0, len(onset_env) - 1)
        score = float(onset_env[idxs].mean())
        if score > best_score:
            best_score, best_phase = score, phase
    downbeats = beat_times[best_phase::BEATS_PER_BAR]
    first_downbeat_s = float(downbeats[0]) if len(downbeats) > 0 else 0.0
    n_bars = len(downbeats)

    # Key
    print("  [analyze] key estimation")
    key = estimate_key(y, sr)

    # Per-bar RMS energy curve
    print("  [analyze] energy curve")
    hop_length = 512
    rms_frames = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    frame_times = librosa.frames_to_time(np.arange(len(rms_frames)), sr=sr, hop_length=hop_length)

    energy_curve = []
    for i in range(n_bars):
        bar_start = downbeats[i]
        bar_end = downbeats[i + 1] if i + 1 < n_bars else duration_s
        mask = (frame_times >= bar_start) & (frame_times < bar_end)
        bar_rms = rms_frames[mask]
        if len(bar_rms) == 0:
            energy_curve.append(0)
            continue
        rms_db = compute_rms_db(bar_rms)
        e = max(0, min(9, int((rms_db + 40) / 4)))
        energy_curve.append(e)

    energy_curve_str = "".join(str(e) for e in energy_curve)
    energy_overall = max(0, min(10, int(np.mean(energy_curve))))

    # Loudness (RMS dBFS — not true LUFS)
    loudness_dbfs = round(compute_rms_db(y), 1)

    # Stem separation
    no_stems = os.environ.get("CLAUDE_DJ_NO_STEMS") == "1"
    if no_stems:
        stem_paths = None
    else:
        print("  [analyze] separating stems (Demucs — may take a while)")
        stem_paths = separate_stems(audio_path, cache_dir)

    # Sections
    print("  [analyze] segmenting structure")
    sections = build_sections(y, sr, downbeats, stem_paths)

    # Cue points: energy-curve-based, snapped to 8-bar phrase boundaries.
    # mix_in  = first phrase boundary after energy sustains at/above mean for 4 bars
    # mix_out = last phrase boundary before energy drops and stays below mean
    cue_points = _energy_cue_points(energy_curve, n_bars)

    title = Path(audio_path).stem
    artist = "Unknown"
    try:
        from mutagen import File as MutagenFile
        tags = MutagenFile(audio_path, easy=True)
        if tags:
            title = str(tags.get("title", [title])[0])
            artist = str(tags.get("artist", [artist])[0])
    except Exception:
        pass

    analysis = TrackAnalysis(
        id=track_id,
        title=title,
        artist=artist,
        file=audio_path,
        duration_s=round(duration_s, 1),
        bpm=round(bpm, 1),
        first_downbeat_s=round(first_downbeat_s, 3),
        key=key,
        energy_overall=energy_overall,
        loudness_dbfs=loudness_dbfs,
        bar_grid=BarGrid(n_bars=n_bars, beats_per_bar=BEATS_PER_BAR),
        energy_curve_per_bar=energy_curve_str,
        sections=sections,
        cue_points=cue_points,
        stems=stem_paths or StemPaths(vocals="", drums="", bass="", other=""),
    )

    d = analysis.to_dict()
    with open(analysis_cache, "w") as f:
        json.dump(d, f, indent=2)

    return analysis


def _dict_to_analysis(d: dict) -> TrackAnalysis:
    d["key"] = KeyInfo(**d["key"])
    d["bar_grid"] = BarGrid(**d["bar_grid"])
    d["stems"] = StemPaths(**d["stems"])
    sections = []
    for s in d["sections"]:
        stems_d = s["stems"]
        for stem_name in stems_d:
            stems_d[stem_name] = StemPresence(**stems_d[stem_name])
        s["stems"] = SectionStems(**stems_d)
        sections.append(Section(**s))
    d["sections"] = sections
    d["cue_points"] = [CuePoint(**c) for c in d["cue_points"]]
    return TrackAnalysis(**d)


def analyze_tracks(audio_paths: list[str]) -> list[TrackAnalysis]:
    return [analyze_track(p, f"T{i+1}") for i, p in enumerate(audio_paths)]
