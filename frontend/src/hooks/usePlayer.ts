import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, buildWsUrl } from '../api';
import type { PlaybackStatus, PlayerState } from '../types';

const SAMPLE_RATE = 44100;
const CHANNELS    = 2;

export function usePlayer(sessionId: string | null) {
  const [playerState,     setPlayerState]     = useState<PlayerState>('idle');
  const [currentBar,      setCurrentBar]      = useState(0);
  const [bufferDepthBars, setBufferDepthBars] = useState(0);

  const wsRef            = useRef<WebSocket | null>(null);
  const ctxRef           = useRef<AudioContext | null>(null);
  const nextTimeRef      = useRef<number>(0);
  const pollRef          = useRef<ReturnType<typeof setInterval> | null>(null);
  const barTimerRef      = useRef<ReturnType<typeof setInterval> | null>(null);

  // Client-side playback tracking (avoids server-side current_bar race
  // where advance() fires when chunks are *sent*, not when they *play*).
  const playStartCtxRef  = useRef<number>(0);   // ctx.currentTime of bar-0 playback
  const secsPerBarRef    = useRef<number>(2.0);  // updated from server status poll
  const startBarRef      = useRef<number>(0);    // bar offset at last seek

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    clearInterval(pollRef.current!);
    clearInterval(barTimerRef.current!);
    nextTimeRef.current     = 0;
    playStartCtxRef.current = 0;
    startBarRef.current     = 0;  // reset seek position for next session
    setPlayerState('idle');
    setCurrentBar(0);
    setBufferDepthBars(0);
  }, []);

  const seek = useCallback((bar: number) => {
    wsRef.current?.send(JSON.stringify({ action: 'seek', bar }));
    const now = ctxRef.current?.currentTime ?? 0;
    // Reset scheduling anchor so post-seek chunks play immediately
    nextTimeRef.current     = now;
    startBarRef.current     = bar;
    playStartCtxRef.current = now;
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    setPlayerState('connecting');
    const ctx = new AudioContext();
    ctxRef.current      = ctx;
    nextTimeRef.current = ctx.currentTime;

    const ws = new WebSocket(buildWsUrl(`/ws/stream/${sessionId}`));
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    let firstChunk = true;

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data) as { type: string };
        if (msg.type === 'loading') { setPlayerState('buffering'); return; }
        if (msg.type === 'end')     { setPlayerState('stopped');   return; }
        if (msg.type === 'error')   { setPlayerState('error');     return; }
        return;
      }

      // Wire format: [uint32 num_samples_per_ch][uint32 sample_rate][float32 stereo PCM...]
      const ab         = ev.data as ArrayBuffer;
      const dv         = new DataView(ab);
      const frameCount = dv.getUint32(0, true);
      const sampleRate = dv.getUint32(4, true) || SAMPLE_RATE;
      const floats     = new Float32Array(ab, 8);

      setPlayerState('playing');
      const buf = ctx.createBuffer(CHANNELS, frameCount, sampleRate);

      for (let ch = 0; ch < CHANNELS; ch++) {
        const channel = buf.getChannelData(ch);
        for (let i = 0; i < frameCount; i++) channel[i] = floats[i * CHANNELS + ch];
      }

      const src  = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);

      const when = Math.max(nextTimeRef.current, ctx.currentTime + 0.08);

      // Resume AudioContext in case autoplay policy suspended it
      if (ctx.state === 'suspended') ctx.resume();

      // Anchor client-side bar clock to when bar-0 audio will actually play.
      if (firstChunk) {
        playStartCtxRef.current = when;
        firstChunk = false;
      }

      src.start(when);
      nextTimeRef.current = when + buf.duration;
    };

    ws.onerror = () => setPlayerState('error');
    ws.onclose = () => {
      clearInterval(barTimerRef.current!);
      clearInterval(pollRef.current!);
      // Don't force 'stopped' — the mix end message sets it cleanly;
      // unexpected drops leave it as 'playing' so UI shows buffering state.
    };

    // Client-side bar counter — driven by AudioContext clock, not server polls.
    // This stays in sync with what's actually playing in the speaker.
    barTimerRef.current = setInterval(() => {
      if (!ctxRef.current || playStartCtxRef.current === 0) return;
      const elapsed = Math.max(0, ctxRef.current.currentTime - playStartCtxRef.current);
      const bar     = startBarRef.current + Math.floor(elapsed / secsPerBarRef.current);
      setCurrentBar(bar);
    }, 200);

    // Fetch ref_bpm and buffer depth from server (low frequency — just for metadata)
    pollRef.current = setInterval(async () => {
      if (!sessionId) return;
      try {
        const res = await apiFetch(`/api/status/${sessionId}`);
        const s   = (await res.json()) as PlaybackStatus;
        // Use server bpm to calibrate bar length; don't use server current_bar
        if (s.ref_bpm && s.ref_bpm > 0) {
          secsPerBarRef.current = (4 * 60) / s.ref_bpm;
        }
        setBufferDepthBars(s.buffer_depth_bars);
      } catch { /* ignore */ }
    }, 2000);

    return stop;
  }, [sessionId, stop]);

  return { playerState, currentBar, bufferDepthBars, seek, stop };
}
