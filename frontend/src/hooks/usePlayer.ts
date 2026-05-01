import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, buildWsUrl } from '../api';
import type { PlaybackStatus, PlayerState } from '../types';

const SAMPLE_RATE = 44100;
const CHANNELS    = 2;

export function usePlayer(sessionId: string | null) {
  const [playerState,     setPlayerState]     = useState<PlayerState>('idle');
  const [currentBar,      setCurrentBar]      = useState(0);
  const [bufferDepthBars, setBufferDepthBars] = useState(0);

  const wsRef       = useRef<WebSocket | null>(null);
  const ctxRef      = useRef<AudioContext | null>(null);
  const nextTimeRef = useRef<number>(0);
  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    clearInterval(pollRef.current!);
    nextTimeRef.current = 0;
    setPlayerState('idle');
    setCurrentBar(0);
    setBufferDepthBars(0);
  }, []);

  const seek = useCallback((bar: number) => {
    wsRef.current?.send(JSON.stringify({ action: 'seek', bar }));
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    setPlayerState('connecting');
    const ctx = new AudioContext();
    ctxRef.current  = ctx;
    nextTimeRef.current = ctx.currentTime;

    const ws = new WebSocket(buildWsUrl(`/ws/stream/${sessionId}`));
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data) as { type: string };
        if (msg.type === 'loading') { setPlayerState('buffering'); return; }
        if (msg.type === 'end')     { setPlayerState('stopped');   return; }
        if (msg.type === 'error')   { setPlayerState('error');     return; }
        return;
      }

      setPlayerState('playing');
      const floats     = new Float32Array(ev.data as ArrayBuffer);
      const frameCount = floats.length / CHANNELS;
      const buf        = ctx.createBuffer(CHANNELS, frameCount, SAMPLE_RATE);

      for (let ch = 0; ch < CHANNELS; ch++) {
        const channel = buf.getChannelData(ch);
        for (let i = 0; i < frameCount; i++) channel[i] = floats[i * CHANNELS + ch];
      }

      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);

      // schedule with 80ms look-ahead to prevent dropouts
      const when = Math.max(nextTimeRef.current, ctx.currentTime + 0.08);
      src.start(when);
      nextTimeRef.current = when + buf.duration;
    };

    ws.onerror = () => setPlayerState('error');
    ws.onclose = () => { /* cleanup handled by stop() */ };

    // Poll playback position every 500ms
    pollRef.current = setInterval(async () => {
      if (!sessionId) return;
      try {
        const res = await apiFetch(`/api/status/${sessionId}`);
        const s   = (await res.json()) as PlaybackStatus;
        setCurrentBar(s.current_bar);
        setBufferDepthBars(s.buffer_depth_bars);
      } catch { /* ignore */ }
    }, 500);

    return stop;
  }, [sessionId, stop]);

  return { playerState, currentBar, bufferDepthBars, seek, stop };
}
