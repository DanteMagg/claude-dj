#!/usr/bin/env python
"""claude-dj — Claude as DJ brain for audio mix generation."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}


def _find_tracks(tracks_dir: str) -> list[str]:
    p = Path(tracks_dir)
    if not p.is_dir():
        raise click.UsageError(f"Not a directory: {tracks_dir}")
    tracks = sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXTS)
    if not tracks:
        raise click.UsageError(f"No audio files found in {tracks_dir}")
    return [str(t) for t in tracks]


@click.group()
def cli():
    pass


@cli.command()
@click.argument("tracks_dir")
@click.option("--output", "-o", default=None, help="Output file [default: outputs/mix_<timestamp>.wav]")
@click.option("--analyze-only", is_flag=True, help="Run analysis only, skip Claude + render")
@click.option("--script", default=None, help="Use existing mix script JSON, skip analysis + Claude")
@click.option("--model", default="claude-sonnet-4-6", show_default=True, help="Claude model to use")
@click.option("--mp3", is_flag=True, help="Export as MP3 instead of WAV")
@click.option("--no-stems", is_flag=True, help="Skip Demucs (faster, disables stem fades)")
def mix(tracks_dir, output, analyze_only, script, model, mp3, no_stems):
    """Analyze TRACKS_DIR, ask Claude to direct the mix, render audio."""
    sys.path.insert(0, str(Path(__file__).parent))

    if no_stems:
        os.environ["CLAUDE_DJ_NO_STEMS"] = "1"

    if script:
        # skip analysis + Claude
        with open(script) as f:
            script_data = json.load(f)
        from schema import MixAction, MixScript, MixTrackRef
        mix_script = MixScript(
            mix_title=script_data["mix_title"],
            reasoning=script_data.get("reasoning", ""),
            tracks=[MixTrackRef(**t) for t in script_data["tracks"]],
            actions=[MixAction(**a) for a in script_data["actions"]],
        )
    else:
        track_paths = _find_tracks(tracks_dir)
        click.echo(f"Found {len(track_paths)} track(s):")
        for i, p in enumerate(track_paths):
            click.echo(f"  T{i+1}: {Path(p).name}")

        click.echo("\nAnalyzing tracks…")
        from analyze import analyze_tracks
        analyses = analyze_tracks(track_paths)

        if analyze_only:
            click.echo("\nAnalysis complete. JSON cached per track.")
            for a in analyses:
                click.echo(f"  {a.id}: {a.title} — {a.bpm:.1f} BPM, {a.key.camelot} ({a.key.standard}), {a.duration_s:.0f}s")
            return

        click.echo("\nAsking Claude to direct the mix…")
        from mix_director import direct_mix
        mix_script = direct_mix(analyses, model)
        click.echo(f"\nReasoning: {mix_script.reasoning[:300]}{'…' if len(mix_script.reasoning) > 300 else ''}")

        # save script
        script_path = Path(tracks_dir) / f"mix_script_{datetime.now():%Y%m%d_%H%M%S}.json"
        import dataclasses
        with open(script_path, "w") as f:
            json.dump(dataclasses.asdict(mix_script), f, indent=2)
        click.echo(f"Mix script saved: {script_path}")

    # normalize (safety layer: clamp DSP values, inject bass_swap if missing)
    from normalizer import normalize
    mix_script = normalize(mix_script)

    # render
    if output is None:
        ext = "mp3" if mp3 else "wav"
        output = str(Path(__file__).parent / "outputs" / f"mix_{datetime.now():%Y%m%d_%H%M%S}.{ext}")

    click.echo(f"\nRendering → {output}")
    from executor import render
    render(mix_script, output, export_mp3=mp3)
    click.echo(f"Done: {output}")


@cli.command()
@click.argument("tracks_dir")
@click.option("--output", "-o", default=None, help="Where to write analysis JSON [default: <tracks_dir>/analysis.json]")
@click.option("--no-stems", is_flag=True, help="Skip Demucs stem separation")
def dump(tracks_dir, output, no_stems):
    """Analyze TRACKS_DIR and write combined analysis JSON (for external Claude session)."""
    sys.path.insert(0, str(Path(__file__).parent))

    if no_stems:
        os.environ["CLAUDE_DJ_NO_STEMS"] = "1"

    track_paths = _find_tracks(tracks_dir)
    click.echo(f"Found {len(track_paths)} track(s):")
    for i, p in enumerate(track_paths):
        click.echo(f"  T{i+1}: {Path(p).name}")

    click.echo("\nAnalyzing tracks…")
    from analyze import analyze_tracks
    analyses = analyze_tracks(track_paths)

    combined = [a.to_dict() for a in analyses]
    out_path = output or str(Path(tracks_dir) / "analysis.json")
    with open(out_path, "w") as f:
        json.dump(combined, f, indent=2)

    click.echo(f"\nAnalysis written to: {out_path}")
    for a in analyses:
        click.echo(f"  {a.id}: {a.title} — {a.bpm:.1f} BPM, {a.key.camelot} ({a.key.standard}), {a.duration_s:.0f}s")


if __name__ == "__main__":
    cli()
