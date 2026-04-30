"""
ChunkScheduler: renders MixScript chunks ahead of playback in a background thread,
feeding an asyncio queue for the /ws/stream WebSocket endpoint.

Wire format per chunk:
  [uint32 little-endian: num_samples_per_channel]
  [uint32 little-endian: sample_rate_hz]
  [float32 little-endian: stereo interleaved PCM ...]
"""
from __future__ import annotations

import asyncio
import struct
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from pydub import AudioSegment

from executor import bars_to_ms, render_chunk
from schema import MixScript

CHUNK_BARS    = 8   # ~16s at 120 BPM
BUFFER_CHUNKS = 4   # keep ~4 chunks (~64s) ahead


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

        self._playback_bar: int = 0  # bar the player is currently at
        self._render_bar:   int = 0  # next bar to render into the buffer

        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=buffer_chunks)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chunk-render")
        self._running  = False
        self._fill_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

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
        self._playback_bar = bar
        self._render_bar   = bar
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def advance(self) -> None:
        """Called by the WebSocket endpoint after each chunk is sent."""
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

    async def _fill_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while self._running:
            if self._queue.full():
                await asyncio.sleep(0.05)
                continue

            bar_start = self._render_bar
            start_ms  = bars_to_ms(bar_start, self.ref_bpm)

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
                pcm = segment_to_pcm(chunk)
                await self._queue.put(pcm)
                self._render_bar += self.chunk_bars
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[ChunkScheduler] render error at bar {bar_start}: {exc}")
                await asyncio.sleep(0.1)
