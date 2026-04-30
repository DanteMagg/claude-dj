import { useCallback, useEffect, useRef, useState } from "react";

export type PlayerState = "idle" | "buffering" | "playing" | "paused" | "error";

interface PlayerStatus {
  state: PlayerState;
  currentBar: number;
  bufferDepthBars: number;
  error: string | null;
}

export interface PlayerControls {
  play: () => void;
  pause: () => void;
  seek: (bar: number) => void;
}

const LOOKAHEAD_S  = 0.4;   // schedule chunks this far ahead of current time
const TICK_MS      = 80;    // scheduler tick interval

export function usePlayer(sessionId: string | null): [PlayerStatus, PlayerControls] {
  const [status, setStatus] = useState<PlayerStatus>({
    state: "idle",
    currentBar: 0,
    bufferDepthBars: 0,
    error: null,
  });

  const wsRef          = useRef<WebSocket | null>(null);
  const ctxRef         = useRef<AudioContext | null>(null);
  const gainRef        = useRef<GainNode | null>(null);
  const nextTimeRef    = useRef<number>(0);
  const chunkQueueRef  = useRef<AudioBuffer[]>([]);
  const currentBarRef  = useRef<number>(0);
  const chunkBarsRef   = useRef<number>(8);     // matches server CHUNK_BARS
  const playingRef     = useRef<boolean>(false);
  const tickRef        = useRef<ReturnType<typeof setInterval> | null>(null);

  const getCtx = useCallback((): AudioContext => {
    if (!ctxRef.current || ctxRef.current.state === "closed") {
      const ctx  = new AudioContext();
      const gain = ctx.createGain();
      gain.connect(ctx.destination);
      ctxRef.current = ctx;
      gainRef.current = gain;
    }
    return ctxRef.current;
  }, []);

  const decodePcmFrame = useCallback(
    (data: ArrayBuffer): AudioBuffer => {
      const view        = new DataView(data);
      const numSamples  = view.getUint32(0, true);
      const sampleRate  = view.getUint32(4, true);
      const pcm         = new Float32Array(data, 8);  // skip 8-byte header

      const ctx = getCtx();
      const buf = ctx.createBuffer(2, numSamples, sampleRate);

      const left  = new Float32Array(numSamples);
      const right = new Float32Array(numSamples);
      for (let i = 0; i < numSamples; i++) {
        left[i]  = pcm[i * 2]     ?? 0;
        right[i] = pcm[i * 2 + 1] ?? 0;
      }
      buf.copyToChannel(left,  0);
      buf.copyToChannel(right, 1);
      return buf;
    },
    [getCtx],
  );

  const scheduleTick = useCallback(() => {
    if (!playingRef.current) return;
    const ctx = ctxRef.current;
    if (!ctx || ctx.state !== "running") return;

    while (
      chunkQueueRef.current.length > 0 &&
      nextTimeRef.current < ctx.currentTime + LOOKAHEAD_S
    ) {
      const buf = chunkQueueRef.current.shift()!;
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(gainRef.current ?? ctx.destination);

      const startAt = Math.max(nextTimeRef.current, ctx.currentTime + 0.01);
      src.start(startAt);
      nextTimeRef.current = startAt + buf.duration;

      currentBarRef.current += chunkBarsRef.current;
    }

    setStatus((prev) => ({
      ...prev,
      state:          playingRef.current ? "playing" : "paused",
      currentBar:     currentBarRef.current,
      bufferDepthBars: chunkQueueRef.current.length * chunkBarsRef.current,
    }));
  }, []);

  const connect = useCallback((id: string) => {
    wsRef.current?.close();
    const ws = new WebSocket(`ws://${window.location.host}/ws/stream/${id}`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus((prev) => ({ ...prev, state: "buffering", error: null }));
    };

    ws.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      try {
        const buf = decodePcmFrame(ev.data);
        chunkQueueRef.current.push(buf);
        if (chunkQueueRef.current.length >= 2 && playingRef.current) {
          setStatus((prev) => ({ ...prev, state: "playing" }));
        }
      } catch (e) {
        console.error("[usePlayer] decode error", e);
      }
    };

    ws.onerror = () => {
      setStatus((prev) => ({ ...prev, state: "error", error: "WebSocket error" }));
    };

    ws.onclose = () => {
      if (playingRef.current) {
        setStatus((prev) => ({ ...prev, state: "error", error: "Connection closed" }));
      }
    };
  }, [decodePcmFrame]);

  useEffect(() => {
    if (!sessionId) return;
    connect(sessionId);
    return () => {
      wsRef.current?.close();
      clearInterval(tickRef.current!);
    };
  }, [sessionId, connect]);

  const play = useCallback(() => {
    const ctx = getCtx();
    if (ctx.state === "suspended") void ctx.resume();
    playingRef.current = true;
    nextTimeRef.current = ctx.currentTime;
    clearInterval(tickRef.current!);
    tickRef.current = setInterval(scheduleTick, TICK_MS);
    setStatus((prev) => ({ ...prev, state: "playing" }));
  }, [getCtx, scheduleTick]);

  const pause = useCallback(() => {
    playingRef.current = false;
    clearInterval(tickRef.current!);
    setStatus((prev) => ({ ...prev, state: "paused" }));
  }, []);

  const seek = useCallback(
    (bar: number) => {
      chunkQueueRef.current  = [];
      currentBarRef.current  = bar;
      nextTimeRef.current    = ctxRef.current ? ctxRef.current.currentTime + 0.05 : 0;
      wsRef.current?.send(JSON.stringify({ action: "seek", bar }));
      setStatus((prev) => ({ ...prev, currentBar: bar, state: "buffering" }));
    },
    [],
  );

  return [status, { play, pause, seek }];
}
