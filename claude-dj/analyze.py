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
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Analysis sample rate — 22050 Hz is the librosa default and halves compute vs 44100 Hz.
# All feature extraction (beat tracking, chroma, MFCCs, RMS) scales with sample count,
# so this alone gives ~2x speedup with negligible accuracy loss for DJ-relevant tasks.
ANALYSIS_SR = 22050

# Cap analysis at 3 minutes — sufficient for section/cue detection.
MAX_ANALYSIS_SECONDS = 180


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
    # chroma_stft is ~10x faster than chroma_cqt with acceptable accuracy for key detection
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=4096, hop_length=1024)
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
    if len(y) == 0:
        return -80.0
    rms = float(np.sqrt(np.mean(y ** 2)))
    if not np.isfinite(rms) or rms < 1e-10:
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
        # hop_length=2048 + n_mfcc=8 → smaller matrix, faster recurrence computation
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=8, hop_length=2048)
        R = librosa.segment.recurrence_matrix(mfcc, mode="affinity", sym=True)
        bounds_frames = librosa.segment.agglomerative(R, k=min(n_segments, len(downbeats) - 1))
        bounds_times = librosa.frames_to_time(bounds_frames, sr=sr)
        bounds_times = np.unique(np.concatenate([[0.0], bounds_times, [librosa.get_duration(y=y, sr=sr)]]))
        return [(float(s), float(e)) for s, e in
                zip(bounds_times[:-1], bounds_times[1:]) if e - s > 0.01]
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


def _classify_section(
    energy: int,
    stems: SectionStems,
    position_ratio: float,
    mean_energy: float,
    has_drop_before: bool,
    has_drop_after: bool,
) -> str:
    """
    Return a semantic section label from audio features and position.

    Priority: drop > intro > outro > breakdown > groove
    """
    drums = stems.drums.presence
    bass  = stems.bass.presence

    # Drop: densest, highest-energy section with strong drums
    if energy >= 7 and drums >= 7:
        return "drop"

    # Intro: low-energy section in the first third of the track
    if energy <= mean_energy and position_ratio < 0.35 and not has_drop_before:
        return "intro"

    # Outro: low-energy section in the last quarter of the track
    if energy <= mean_energy and position_ratio > 0.72:
        return "outro"

    # Breakdown: sparse/melodic section after a drop (drums fade, bass gone)
    if (energy < mean_energy and drums <= 4
            and (has_drop_before or position_ratio > 0.30)):
        return "breakdown"

    # Groove: everything else — main body, sustained energy
    return "groove"


def build_sections(
    y: np.ndarray,
    sr: int,
    downbeats: np.ndarray,
    stem_paths: Optional[StemPaths],
) -> list[Section]:
    segments = segment_audio(y, sr, downbeats)
    n_bars = len(downbeats)

    # load stems once (skip if --no-stems)
    stem_arrays: dict[str, np.ndarray] = {}
    stem_srs: dict[str, int] = {}
    stem_max_rms: dict[str, float] = {}
    if stem_paths is not None:
        for stem_name in ("vocals", "drums", "bass", "other"):
            path = getattr(stem_paths, stem_name)
            s_y, s_sr = librosa.load(path, sr=ANALYSIS_SR, mono=True)
            stem_arrays[stem_name] = s_y
            stem_srs[stem_name] = s_sr
            stem_max_rms[stem_name] = compute_rms_db(s_y)

    # First pass: collect raw section data without semantic labels
    raw: list[dict] = []
    for start_s, end_s in segments:
        start_bar = time_to_bar(start_s, downbeats)
        end_bar   = time_to_bar(end_s,   downbeats)

        start_sample = librosa.time_to_samples(start_s, sr=sr)
        end_sample   = librosa.time_to_samples(end_s,   sr=sr)
        y_seg        = y[start_sample:end_sample]
        mix_rms_db   = compute_rms_db(y_seg)
        if np.isnan(mix_rms_db):
            mix_rms_db = -80.0
        energy = max(0, min(10, int((mix_rms_db + 40) / 4)))

        if stem_arrays:
            stem_presences: dict[str, StemPresence] = {}
            for stem_name, s_y in stem_arrays.items():
                s_sr = stem_srs[stem_name]
                s_start = librosa.time_to_samples(start_s, sr=s_sr)
                s_end   = librosa.time_to_samples(end_s,   sr=s_sr)
                seg     = s_y[s_start:s_end]
                rms     = compute_rms_db(seg)
                pres    = presence_from_rms(rms, stem_max_rms[stem_name])
                stem_presences[stem_name] = StemPresence(presence=pres, rms_db=round(rms, 1))
            section_stems = SectionStems(**stem_presences)
        else:
            section_stems = ABSENT_STEMS

        raw.append({
            "start_bar": start_bar, "end_bar": end_bar,
            "start_s": round(start_s, 2), "end_s": round(end_s, 2),
            "energy": energy, "mix_rms_db": mix_rms_db, "stems": section_stems,
        })

    if not raw:
        return []

    mean_energy = sum(r["energy"] for r in raw) / len(raw)

    # Pre-compute which sections contain drops (for context in classifier)
    drop_mask = [
        r["energy"] >= 7 and r["stems"].drums.presence >= 7
        for r in raw
    ]

    sections: list[Section] = []
    for i, r in enumerate(raw):
        has_drop_before = any(drop_mask[:i])
        has_drop_after  = any(drop_mask[i + 1:])
        pos_ratio       = r["start_bar"] / max(1, n_bars)

        label = _classify_section(
            r["energy"], r["stems"], pos_ratio,
            mean_energy, has_drop_before, has_drop_after,
        )

        sections.append(Section(
            label=label,
            start_bar=r["start_bar"],
            end_bar=r["end_bar"],
            start_s=r["start_s"],
            end_s=r["end_s"],
            energy=r["energy"],
            loudness_dbfs=round(r["mix_rms_db"], 1),
            stems=r["stems"],
        ))

    return sections


def _cue_points_from_sections(
    sections: list[Section],
    energy_curve: list[int],
    n_bars: int,
) -> list[CuePoint]:
    """
    Derive precise DJ cue points from semantic sections + energy curve.

    Returns: mix_in, mix_out, and optionally drop_bar, breakdown_start, outro_start.
    All bars snapped to the nearest 8-bar phrase boundary.
    """
    phrase = 8
    cues: list[CuePoint] = []

    def _snap(bar: int) -> int:
        return (bar // phrase) * phrase

    # ── mix_in: end of intro (first non-intro section start) ──────────────────
    mix_in = 0
    for s in sections:
        if s.label != "intro":
            mix_in = _snap(s.start_bar)
            break

    # Fallback: energy-curve heuristic if no sections or all intro
    if mix_in == 0 and energy_curve:
        n = len(energy_curve)
        mean_e = sum(energy_curve) / n
        for i in range(n - 3):
            if all(e >= mean_e for e in energy_curve[i:i + 4]):
                mix_in = _snap(i)
                break

    cues.append(CuePoint(name="mix_in", bar=mix_in, type="phrase_start"))

    # ── drop_bar: first drop section ──────────────────────────────────────────
    for s in sections:
        if s.label == "drop":
            drop_bar = _snap(s.start_bar)
            cues.append(CuePoint(name="drop_bar", bar=drop_bar, type="phrase_start"))
            break

    # ── breakdown_start: first breakdown section ───────────────────────────────
    for s in sections:
        if s.label == "breakdown":
            bd_bar = _snap(s.start_bar)
            cues.append(CuePoint(name="breakdown_start", bar=bd_bar, type="phrase_start"))
            break

    # ── outro_start / mix_out: last outro or last low-energy section ───────────
    outro_bar = None
    for s in reversed(sections):
        if s.label in ("outro", "breakdown"):
            outro_bar = _snap(s.start_bar)
            break

    # Fallback: energy-curve backward scan in second half
    if outro_bar is None and energy_curve:
        n   = len(energy_curve)
        half = n // 2
        mean_e = sum(energy_curve) / n
        for i in range(n - 4, max(half, 0), -1):
            if all(e >= mean_e for e in energy_curve[i:i + 4]):
                outro_bar = min(n_bars - 1, _snap(i + 4))
                break
        if outro_bar is None:
            outro_bar = _snap(max(0, n_bars - phrase * 2))

    mix_out = outro_bar or _snap(max(0, n_bars - phrase * 2))
    cues.append(CuePoint(name="mix_out", bar=mix_out, type="outro_start"))

    return cues


def analyze_track(audio_path: str, track_id: str, no_stems: bool = False) -> TrackAnalysis:
    audio_path = str(Path(audio_path).resolve())
    cache_dir = track_cache_dir(audio_path)
    analysis_cache = cache_dir / "analysis.json"

    if analysis_cache.exists():
        with open(analysis_cache) as f:
            d = json.load(f)
        d["id"]   = track_id   # always use the caller-assigned id, not the cached one
        d["file"] = audio_path  # always use the current resolved path, not the cached one
        return _dict_to_analysis(d)

    print(f"  [analyze] loading {Path(audio_path).name}")
    # Resample to ANALYSIS_SR on load — halves data size vs 44100 Hz with negligible
    # quality loss for beat/key/energy tasks. Also cap at MAX_ANALYSIS_SECONDS.
    y_full, sr = librosa.load(audio_path, sr=ANALYSIS_SR, mono=True)
    full_duration_s = float(librosa.get_duration(y=y_full, sr=sr))
    y = y_full[: sr * MAX_ANALYSIS_SECONDS] if len(y_full) > sr * MAX_ANALYSIS_SECONDS else y_full
    duration_s = full_duration_s  # report real track duration, not capped analysis window

    # Parallel feature extraction: beat tracking and key estimation are independent
    # and each takes ~5-15 s alone; running together saves that time.
    print("  [analyze] beat tracking + key (parallel)")
    hop_length = 512

    def _beat_and_onset():
        t, bf = librosa.beat.beat_track(y=y, sr=sr, units="frames", hop_length=hop_length)
        bt = librosa.frames_to_time(bf, sr=sr, hop_length=hop_length)
        oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        return float(np.atleast_1d(t)[0]), bt, oe

    def _rms():
        return librosa.feature.rms(y=y, hop_length=hop_length)[0]

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_beat  = pool.submit(_beat_and_onset)
        f_key   = pool.submit(estimate_key, y, sr)
        f_rms   = pool.submit(_rms)
        bpm, beat_times, onset_env = f_beat.result()
        key      = f_key.result()
        rms_frames = f_rms.result()

    # Downbeat phase correction: try all 4 offsets, pick the one where downbeats
    # land on strongest onsets (beat 1 of each bar has the strongest transient on
    # average, e.g. kick drum + chord hit).
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop_length)
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

    # ── Downbeat confidence diagnostics ─────────────────────────────────────
    # Warn when the beat grid is shaky so we know before the mix uses bad data.
    _name = Path(audio_path).name
    if len(beat_times) >= 8:
        ibi = np.diff(beat_times)                 # inter-beat intervals
        ibi_cv = float(ibi.std() / max(ibi.mean(), 1e-6))   # coeff of variation
        if ibi_cv > 0.15:
            print(f"  [analyze] WARNING {_name}: beat grid unstable "
                  f"(IBI coeff-of-variation={ibi_cv:.2f} > 0.15) — "
                  f"downbeat/BPM may be unreliable")
    # Phase-selection margin: how much better is the winning phase vs the worst?
    all_scores = []
    for phase in range(BEATS_PER_BAR):
        cand = beat_times[phase::BEATS_PER_BAR]
        idxs = np.searchsorted(onset_times, cand).clip(0, len(onset_env) - 1)
        all_scores.append(float(onset_env[idxs].mean()))
    phase_margin = best_score - min(all_scores)
    if phase_margin < 0.05 * max(best_score, 1e-6):
        print(f"  [analyze] WARNING {_name}: low phase-selection confidence "
              f"(margin={phase_margin:.4f}) — downbeat phase may be off by 1–3 beats")
    # Sanity-check the estimated first downbeat against track duration
    if first_downbeat_s > 8.0:
        print(f"  [analyze] WARNING {_name}: first_downbeat_s={first_downbeat_s:.2f}s "
              f"is unusually large — track may have a long non-beat intro; "
              f"verify the downbeat trim is correct")

    # Per-bar RMS energy curve (rms_frames already computed in parallel above)
    print("  [analyze] energy curve")
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
    if no_stems:
        stem_paths = None
    else:
        print("  [analyze] separating stems (Demucs — may take a while)")
        stem_paths = separate_stems(audio_path, cache_dir)

    # Sections
    print("  [analyze] segmenting structure")
    sections = build_sections(y, sr, downbeats, stem_paths)

    # Cue points derived from semantic sections + energy curve
    cue_points = _cue_points_from_sections(sections, energy_curve, n_bars)

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
    # migrate renamed field from old cache files
    if "loudness_lufs" in d:
        d["loudness_dbfs"] = d.pop("loudness_lufs")
    return TrackAnalysis(**d)


def analyze_tracks(audio_paths: list[str], no_stems: bool = False) -> list[TrackAnalysis]:
    return [analyze_track(p, f"T{i+1}", no_stems=no_stems) for i, p in enumerate(audio_paths)]


def analyze_transition_zone(
    audio_path: str,
    bpm: float,
    first_downbeat_s: float,
    start_bar: int,
    n_bars: int = 48,
) -> list[dict]:
    """
    Fast per-bar deep analysis of a transition window (entry or exit zone).

    Returns a list of dicts, one per bar:
      {"bar": 80, "drums": 0.82, "harmonic": 0.71,
       "brightness": 0.65, "onsets": 4, "rms": 0.75}

    "drums" and "harmonic" are normalised 0–1 RMS values from:
      - Demucs cached stems (drums.wav / bass+other.wav) if available
      - HPSS percussive/harmonic decomposition otherwise

    "brightness" is normalised spectral centroid (0=dark, 1=bright).
    "onsets" is onset count per bar (0–4 scale, proxy for beat density).
    """
    audio_path = str(Path(audio_path).resolve())
    secs_per_bar = 4 * 60.0 / bpm

    zone_start_s = first_downbeat_s + start_bar * secs_per_bar
    zone_dur_s   = n_bars * secs_per_bar

    # Load only the zone slice to keep this fast
    y_full, sr = librosa.load(
        audio_path, sr=ANALYSIS_SR, mono=True,
        offset=max(0.0, zone_start_s),
        duration=zone_dur_s,
    )
    if len(y_full) == 0:
        return []

    actual_bars = min(n_bars, max(1, int(len(y_full) / (secs_per_bar * sr))))

    # ── Source: real Demucs stems (if cached) or HPSS fallback ───────────────
    cache_dir = CACHE_DIR / file_hash(audio_path)
    drums_stem_path = cache_dir / "stems" / "drums.wav"
    bass_stem_path  = cache_dir / "stems" / "bass.wav"
    other_stem_path = cache_dir / "stems" / "other.wav"
    has_stems = drums_stem_path.exists() and bass_stem_path.exists()

    if has_stems:
        drums_y, _ = librosa.load(
            str(drums_stem_path), sr=ANALYSIS_SR, mono=True,
            offset=max(0.0, zone_start_s), duration=zone_dur_s,
        )
        # harmonic = bass + other (everything non-percussive)
        bass_y, _ = librosa.load(
            str(bass_stem_path), sr=ANALYSIS_SR, mono=True,
            offset=max(0.0, zone_start_s), duration=zone_dur_s,
        )
        harm_len = min(len(y_full), len(bass_y))
        if other_stem_path.exists():
            other_y, _ = librosa.load(
                str(other_stem_path), sr=ANALYSIS_SR, mono=True,
                offset=max(0.0, zone_start_s), duration=zone_dur_s,
            )
            harm_len = min(harm_len, len(other_y))
            harmonic_y = bass_y[:harm_len] + other_y[:harm_len]
        else:
            harmonic_y = bass_y[:harm_len]
        drums_y = drums_y[:harm_len]
        y_full  = y_full[:harm_len]
    else:
        # HPSS: fast enough on a 48-bar slice (~0.5s at 22 kHz)
        harmonic_y, drums_y = librosa.effects.hpss(y_full, margin=3.0)

    # Normalise against the zone peak so values are relative (0–1)
    mix_peak  = float(np.sqrt(np.mean(y_full  ** 2))) + 1e-9
    drum_peak = float(np.sqrt(np.mean(drums_y ** 2))) + 1e-9
    harm_peak = float(np.sqrt(np.mean(harmonic_y ** 2))) + 1e-9
    zone_peak = max(mix_peak, 1e-6)

    # Pre-compute onset envelope over the whole zone for peak-picking
    hop = 256
    onset_env = librosa.onset.onset_strength(y=y_full, sr=sr, hop_length=hop)
    frames_per_bar = max(1, int(secs_per_bar * sr / hop))

    results: list[dict] = []
    for i in range(actual_bars):
        bar_abs = start_bar + i
        s = int(i * secs_per_bar * sr)
        e = int((i + 1) * secs_per_bar * sr)

        mix_slice  = y_full[s:e]
        drum_slice = drums_y[s:e]
        harm_slice = harmonic_y[s:e]

        if len(mix_slice) == 0:
            break

        # RMS — normalised to zone peak so they're comparable across bars
        mix_rms  = float(np.sqrt(np.mean(mix_slice  ** 2))) / zone_peak
        drum_rms = float(np.sqrt(np.mean(drum_slice ** 2))) / zone_peak
        harm_rms = float(np.sqrt(np.mean(harm_slice ** 2))) / zone_peak

        # Spectral centroid → brightness (500 Hz = dark, 8000 Hz = bright)
        sc = librosa.feature.spectral_centroid(y=mix_slice, sr=sr, hop_length=hop)
        sc_mean = float(np.mean(sc))
        brightness = min(1.0, max(0.0, (sc_mean - 500.0) / 7500.0))

        # Onset count in this bar (0–4 scale)
        of_s = i * frames_per_bar
        of_e = (i + 1) * frames_per_bar
        bar_onset = onset_env[of_s:of_e] if of_e <= len(onset_env) else onset_env[of_s:]
        if len(bar_onset) > 0:
            threshold = float(np.mean(onset_env)) * 0.8
            onsets = int(np.sum(bar_onset > threshold))
            onsets = min(4, onsets)
        else:
            onsets = 0

        results.append({
            "bar":        bar_abs,
            "drums":      round(min(1.0, drum_rms * 1.5), 2),  # slight boost for legibility
            "harmonic":   round(min(1.0, harm_rms * 1.5), 2),
            "brightness": round(brightness, 2),
            "onsets":     onsets,
            "rms":        round(min(1.0, mix_rms), 2),
        })

    return results
