"""
ChunkScheduler: renders MixScript chunks ahead of playback in a background thread,
feeding an asyncio queue for the /ws/stream WebSocket endpoint.

Wire format per audio chunk:
  [uint32 little-endian: num_samples_per_channel]
  [uint32 little-endian: sample_rate_hz]
  [float32 little-endian: stereo interleaved PCM ...]

End-of-mix sentinel: a 2-byte frame b"\\xff\\xff" (no valid audio has this header).
The client should treat this as "mix complete" and stop requesting chunks.
"""
from __future__ import annotations

import asyncio
import struct
import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from pydub import AudioSegment

from executor import bars_to_ms, render_chunk
from schema import MixAction, MixScript

CHUNK_BARS    = 8   # ~16s at 120 BPM
BUFFER_CHUNKS = 4   # keep ~4 chunks (~64s) ahead
# Never render more than this many seconds ahead of actual playback.
# Keep tight: a large lookahead forces transitions further into the future (the
# render-head bound dominates the offset calculation) which causes the outgoing
# track's audio to run dry before the incoming track arrives.
MAX_LOOKAHEAD_SECS = 30.0

# Sentinel value sent to the client when the mix ends
MIX_END_SENTINEL = b"\xff\xff"


def segment_to_pcm(seg: AudioSegment) -> bytes:
    """
    Convert a pydub AudioSegment to the wire format:
    [uint32 num_samples_per_ch][uint32 sample_rate][float32 stereo interleaved PCM]
    """
    if seg.channels == 1:
        seg = seg.set_channels(2)

    max_val = float(1 << (seg.sample_width * 8 - 1))
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32) / max_val
    num_samples_per_ch = len(samples) // 2

    header = struct.pack("<II", num_samples_per_ch, seg.frame_rate)
    return header + samples.astype("<f4").tobytes()


def _total_mix_ms(script: MixScript, ref_bpm: float) -> int:
    """Estimate the mix end time from the latest scheduled action."""
    max_bar = 0
    for a in script.actions:
        bar = (a.at_bar or a.start_bar or a.bar or 0) + (a.duration_bars or 0)
        if bar > max_bar:
            max_bar = bar
    return bars_to_ms(max_bar + 16, ref_bpm)  # +16 bars tail room


class ChunkScheduler:
    def __init__(
        self,
        script: MixScript,
        loaded: dict[str, AudioSegment],
        stem_layers: dict[tuple[str, str], AudioSegment],
        ref_bpm: float,
        chunk_bars: int = CHUNK_BARS,
        buffer_chunks: int = BUFFER_CHUNKS,
    ):
        self.script        = script
        self.loaded        = loaded
        self.stem_layers   = stem_layers
        self.ref_bpm       = ref_bpm
        self.chunk_bars    = chunk_bars
        self.chunk_ms      = bars_to_ms(chunk_bars, ref_bpm)
        self.buffer_chunks = buffer_chunks
        # Set total_mix_ms to cover the actual loaded audio, not just the last action bar.
        # _total_mix_ms only adds 16 bars tail, which can cut off a long last track early.
        script_ms   = _total_mix_ms(script, ref_bpm)
        max_play_ms = max((len(seg) for seg in loaded.values()), default=0)
        self.total_mix_ms = max(script_ms, max_play_ms)
        print(f"[ChunkScheduler] init: script_ms={script_ms}, max_play_ms={max_play_ms}, total_mix_ms={self.total_mix_ms}")

        self._playback_bar: int = 0  # bar the player is currently at
        self._render_bar:   int = 0  # next bar to render into the buffer

        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=buffer_chunks)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chunk-render")
        self._running  = False
        self._fill_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

        # Epoch incremented by seek() so in-flight renders can detect staleness.
        # Only read/written from the asyncio event-loop thread — no mutex needed.
        self._render_epoch: int = 0

        # Wall-clock time when the first chunk was dequeued (bar 0 started "playing").
        # Used to pace rendering and prevent racing far ahead of actual playback.
        self._wall_play_start: float = 0.0

    async def start(self) -> None:
        self._running   = True
        self._fill_task = asyncio.create_task(self._fill_loop())

    async def stop(self) -> None:
        self._running = False
        if self._fill_task:
            self._fill_task.cancel()
        self._executor.shutdown(wait=False)

    def seek(self, bar: int) -> None:
        """Reposition to a different bar — drains the stale buffer."""
        self._playback_bar   = bar
        self._render_bar     = bar
        self._render_epoch  += 1
        self._wall_play_start = _time.monotonic() - bar * (4 * 60 / self.ref_bpm)
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def advance(self) -> None:
        """Called by the WebSocket endpoint after each chunk is sent."""
        if self._wall_play_start == 0.0:
            # Record when bar 0 first left the server — proxy for "playback started".
            self._wall_play_start = _time.monotonic()
        self._playback_bar += self.chunk_bars

    async def get_chunk(self) -> bytes:
        """Block until the next rendered chunk is available."""
        return await self._queue.get()

    @property
    def current_bar(self) -> int:
        return self._playback_bar

    @property
    def buffer_depth_bars(self) -> int:
        return self._queue.qsize() * self.chunk_bars

    def extend(
        self,
        new_script: MixScript,
        extra_loaded: "dict[str, AudioSegment]",
        extra_stems: "dict[tuple[str, str], AudioSegment] | None" = None,
    ) -> None:
        """
        Atomically extend the live mix with new tracks/actions without stopping playback.

        The in-flight render_chunk call in the thread pool holds a reference to the
        OLD script object and completes safely. The next _fill_loop iteration picks up
        new_script. dict.update() is atomic enough under CPython's GIL.
        """
        self.loaded.update(extra_loaded)
        if extra_stems:
            self.stem_layers.update(extra_stems)
        self.script = new_script          # replace last — next render sees new script

        # Compute end time: script-based estimate PLUS the last track's actual duration.
        # Without this, the sentinel fires ~16 bars after the last action, cutting off T2
        # just seconds after its play action.
        script_ms = _total_mix_ms(new_script, self.ref_bpm)
        last_play_end_ms = 0
        for a in new_script.actions:
            if a.type == "play" and a.track in self.loaded:
                play_ms = bars_to_ms(a.at_bar or 0, self.ref_bpm)
                last_play_end_ms = max(last_play_end_ms, play_ms + len(self.loaded[a.track]))
        self.total_mix_ms = max(script_ms, last_play_end_ms)
        print(f"[ChunkScheduler] extend: script_ms={script_ms} last_play_end_ms={last_play_end_ms} total_mix_ms={self.total_mix_ms}")

    async def _fill_loop(self) -> None:
        loop = asyncio.get_running_loop()
        secs_per_bar = 4 * 60 / self.ref_bpm

        while self._running:
            if self._queue.full():
                await asyncio.sleep(0.05)
                continue

            bar_start = self._render_bar
            start_ms  = bars_to_ms(bar_start, self.ref_bpm)
            epoch     = self._render_epoch  # snapshot before yield point

            # Pace rendering: don't get more than MAX_LOOKAHEAD_SECS ahead of actual playback.
            # This ensures transitions loaded by dj_worker can still be mixed into unsent chunks.
            if self._wall_play_start > 0.0:
                elapsed_real = _time.monotonic() - self._wall_play_start
                rendered_secs = bar_start * secs_per_bar
                if rendered_secs > elapsed_real + MAX_LOOKAHEAD_SECS:
                    await asyncio.sleep(1.0)
                    continue

            # Past the end of the mix — send sentinel and stop filling
            if start_ms >= self.total_mix_ms:
                print(f"[ChunkScheduler] sentinel at bar {bar_start}, start_ms={start_ms}, total_mix_ms={self.total_mix_ms}")
                await self._queue.put(MIX_END_SENTINEL)
                self._running = False
                break

            try:
                chunk: AudioSegment = await loop.run_in_executor(
                    self._executor,
                    render_chunk,
                    self.script,
                    self.loaded,
                    self.stem_layers,
                    self.ref_bpm,
                    start_ms,
                    self.chunk_ms,
                )
                if epoch != self._render_epoch:  # seek() fired while we were rendering
                    continue
                pcm = segment_to_pcm(chunk)
                await self._queue.put(pcm)
                self._render_bar += self.chunk_bars
            except asyncio.CancelledError:
                break
            except Exception as exc:
                # Transient error (e.g. track not yet loaded) — back off and retry.
                # After 30 retries (~3s) on the same bar, emit silence and advance to
                # avoid a permanent stall; silence is better than hanging the stream.
                if not hasattr(self, '_err_bar') or self._err_bar != bar_start:
                    self._err_bar = bar_start
                    self._err_count = 0
                self._err_count += 1
                if self._err_count >= 30:
                    print(f"[ChunkScheduler] skipping stuck bar {bar_start} after {self._err_count} retries: {exc}")
                    target_rate = next(
                        (v.frame_rate for v in self.loaded.values()), 44100
                    )
                    silence = AudioSegment.silent(duration=self.chunk_ms, frame_rate=target_rate)
                    if epoch == self._render_epoch:
                        await self._queue.put(segment_to_pcm(silence))
                        self._render_bar += self.chunk_bars
                    self._err_count = 0
                else:
                    print(f"[ChunkScheduler] render error at bar {bar_start} (retry {self._err_count}): {exc}")
                    await asyncio.sleep(0.1)
