# Claude DJ Frontend Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `frontend/src/` from scratch with a Rekordbox-style deck layout, Geist fonts, orange/blue deck identity, A+B waveform overlay, and a typewriter reasoning reveal for Claude's planning state.

**Architecture:** React 19 + TypeScript + Vite (unchanged). Three custom hooks own all state (`useLibrary`, `useDjSession`, `usePlayer`). Components are pure presentational — they receive props, fire callbacks. `App.tsx` is the only place where hooks are called and wired together. CSS grid layout with a collapsible library drawer that pushes content up when opened.

**Tech Stack:** React 19, TypeScript, Vite, WebAudio API, Canvas 2D API, Geist fonts (Google Fonts CDN). No new npm dependencies.

**Important:** `window.electron.selectFolder()` (not `electronAPI.openFolder`) — confirmed from `frontend/electron/preload.cjs`. `DjDeckB` from the API has only `status` and `title` — no `hash` field. Deck B waveform curve is looked up by title-match as best-effort.

---

## Task 1: CSS Foundation

**Files:**
- Create: `frontend/src/index.css`
- Create: `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Create `frontend/src/vite-env.d.ts`**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 2: Create `frontend/src/index.css`**

```css
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #080808;
  --surface:   #0e0e0e;
  --surface2:  #141414;
  --border:    #1e1e1e;
  --border2:   #2a2a2a;

  --orange:    #ff5f00;
  --orange-lo: rgba(255,95,0,0.08);
  --blue:      #00b4ff;
  --blue-lo:   rgba(0,180,255,0.08);
  --purple:    #bf5af2;
  --green:     #30d158;
  --yellow:    #ffd60a;
  --red:       #ff375f;

  --text:      #e8e8e8;
  --text-2:    #666;
  --text-3:    #333;

  --font-ui:   'Geist', system-ui, sans-serif;
  --font-mono: 'Geist Mono', ui-monospace, monospace;
}

html, body, #root {
  height: 100%;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 13px;
  line-height: 1.4;
  -webkit-font-smoothing: antialiased;
}

button { cursor: pointer; border: none; background: none; color: inherit; font: inherit; }

input, select {
  font: inherit;
  color: var(--text);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 5px 9px;
  outline: none;
}
input:focus, select:focus { border-color: var(--orange); }

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

@keyframes blink {
  50% { opacity: 0; }
}
@keyframes pulse {
  0%, 100% { opacity: 0.7; }
  50%       { opacity: 1; }
}
@keyframes pulse-ring {
  0%, 100% { box-shadow: 0 0 0 0 rgba(191,90,242,0.3); }
  50%       { box-shadow: 0 0 0 4px rgba(191,90,242,0.1); }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css frontend/src/vite-env.d.ts
git commit -m "feat(frontend): css variables, resets, keyframes"
```

---

## Task 2: Types

**Files:**
- Create: `frontend/src/types.ts`

- [ ] **Step 1: Create `frontend/src/types.ts`**

```typescript
export interface CuePoint {
  name: string;
  bar: number;
  type: string;
}

export interface LibraryTrack {
  hash: string;
  path: string;
  title: string;
  artist: string;
  bpm: number;
  key_camelot: string;
  key_standard: string;
  energy: number;
  duration_s: number;
  energy_curve: string;
  cue_points: CuePoint[];
  first_downbeat_s: number;
  analyzed_at: string;
}

export interface LibraryScanJob {
  status: 'running' | 'done' | 'error';
  progress: number;
  total: number;
  known: number;
  new: number;
  skipped?: number;
  error: string | null;
}

// deck_a always has a hash; deck_b only has status + title (backend limitation)
export interface DjDeck {
  track_id: string;
  hash: string;
  title: string;
  start_bar: number;
  status: string;
}

export interface DjDeckB {
  status: 'starting' | 'analyzing' | 'planning' | 'loading' | 'ready';
  title: string;
}

export interface MixAction {
  type: string;
  track: string;
  at_bar: number | null;
  from_bar: number | null;
  to_bar: number | null;
  bar: number | null;
  start_bar: number | null;
}

export interface MixTrackRef {
  id: string;
  path: string;
  bpm: number;
  first_downbeat_s: number;
}

export interface MixScript {
  mix_title: string;
  reasoning: string;
  tracks: MixTrackRef[];
  actions: MixAction[];
}

export interface DjState {
  status: 'starting' | 'playing' | 'error';
  session_id: string | null;
  deck_a: DjDeck | null;
  deck_b: DjDeckB | null;
  ref_bpm: number | null;
  queue: string[];
  history: string[];
  script: MixScript | null;
  error: string | null;
}

export interface PlaybackStatus {
  current_bar: number;
  buffer_depth_bars: number;
  ref_bpm: number;
  status: string;
}

export type PlayerState = 'idle' | 'connecting' | 'buffering' | 'playing' | 'stopped' | 'error';

export interface DjStartOpts {
  pool: string[];
  queue: string[];
  let_claude_pick: boolean;
  model: string;
}

// Electron bridge (exposed by preload.cjs)
declare global {
  interface Window {
    electron?: {
      selectFolder: () => Promise<string | null>;
      showInFolder: (path: string) => Promise<void>;
      isElectron: boolean;
    };
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat(frontend): type definitions"
```

---

## Task 3: API Utilities + Entry Point

**Files:**
- Create: `frontend/src/api.ts`
- Create: `frontend/src/main.tsx`

- [ ] **Step 1: Create `frontend/src/api.ts`**

```typescript
// Vite dev server proxies /api → http://127.0.0.1:8000 and /ws → ws://127.0.0.1:8000
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, init);
}

export function buildWsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}${path}`;
}
```

- [ ] **Step 2: Create `frontend/src/main.tsx`**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts frontend/src/main.tsx
git commit -m "feat(frontend): api utilities and entry point"
```

---

## Task 4: useLibrary Hook

**Files:**
- Create: `frontend/src/hooks/useLibrary.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useLibrary.ts`**

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';
import type { LibraryScanJob, LibraryTrack } from '../types';

export function useLibrary() {
  const [tracks, setTracks]   = useState<LibraryTrack[]>([]);
  const [scanJob, setScanJob] = useState<LibraryScanJob | null>(null);
  const [scanId, setScanId]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLibrary = useCallback(async () => {
    try {
      const res  = await apiFetch('/api/library');
      const data = (await res.json()) as { tracks: LibraryTrack[] };
      setTracks(data.tracks);
    } catch { /* ignore transient */ }
  }, []);

  useEffect(() => { void fetchLibrary(); }, [fetchLibrary]);

  // Poll scan job until done
  useEffect(() => {
    if (!scanId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/library/scan/${scanId}`);
        const job = (await res.json()) as LibraryScanJob;
        setScanJob(job);
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(pollRef.current!);
          if (job.status === 'done') void fetchLibrary();
        }
      } catch { /* ignore */ }
    }, 1000);
    return () => clearInterval(pollRef.current!);
  }, [scanId, fetchLibrary]);

  const scanFolder = useCallback(async (folder: string) => {
    setScanJob({ status: 'running', progress: 0, total: 0, known: 0, new: 0, error: null });
    try {
      const res  = await apiFetch('/api/library/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder }),
      });
      const data = (await res.json()) as { scan_id?: string; error?: string };
      if (data.error) {
        setScanJob({ status: 'error', progress: 0, total: 0, known: 0, new: 0, error: data.error });
      } else if (data.scan_id) {
        setScanId(data.scan_id);
      }
    } catch (e) {
      setScanJob({ status: 'error', progress: 0, total: 0, known: 0, new: 0, error: String(e) });
    }
  }, []);

  // Look up a track by hash (O(n) but library is small)
  const trackByHash = useCallback(
    (hash: string): LibraryTrack | undefined => tracks.find(t => t.hash === hash),
    [tracks],
  );

  // Best-effort lookup by title (for deck_b which has no hash in the API response)
  const trackByTitle = useCallback(
    (title: string): LibraryTrack | undefined => tracks.find(t => t.title === title),
    [tracks],
  );

  return { tracks, scanJob, scanFolder, fetchLibrary, trackByHash, trackByTitle };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useLibrary.ts
git commit -m "feat(frontend): useLibrary hook"
```

---

## Task 5: useDjSession Hook

**Files:**
- Create: `frontend/src/hooks/useDjSession.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useDjSession.ts`**

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';
import type { DjStartOpts, DjState } from '../types';

export function useDjSession() {
  const [djId,    setDjId]    = useState<string | null>(null);
  const [djState, setDjState] = useState<DjState | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!djId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res   = await apiFetch(`/api/dj/${djId}`);
        const state = (await res.json()) as DjState;
        setDjState(state);
        if (state.status === 'error') {
          setError(state.error);
          clearInterval(pollRef.current!);
        }
      } catch { /* ignore transient */ }
    }, 1500);
    return () => clearInterval(pollRef.current!);
  }, [djId]);

  const startDj = useCallback(async (opts: DjStartOpts) => {
    setError(null);
    try {
      const res  = await apiFetch('/api/dj/start', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(opts),
      });
      const data = (await res.json()) as { dj_id?: string; error?: string };
      if (data.error) { setError(data.error); return; }
      if (data.dj_id) setDjId(data.dj_id);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const stopDj = useCallback(() => {
    clearInterval(pollRef.current!);
    setDjId(null);
    setDjState(null);
    setError(null);
  }, []);

  const enqueue = useCallback(async (hash: string) => {
    if (!djId) return;
    try {
      await apiFetch(`/api/dj/${djId}/queue`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ hash }),
      });
    } catch { /* ignore */ }
  }, [djId]);

  return { djId, djState, error, startDj, stopDj, enqueue };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useDjSession.ts
git commit -m "feat(frontend): useDjSession hook"
```

---

## Task 6: usePlayer Hook

**Files:**
- Create: `frontend/src/hooks/usePlayer.ts`

The backend streams float32 PCM interleaved stereo at 44100 Hz. Each WebSocket binary message is one chunk (~1 second). The hook schedules chunks through Web Audio API with a small look-ahead to prevent dropouts.

- [ ] **Step 1: Create `frontend/src/hooks/usePlayer.ts`**

```typescript
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/usePlayer.ts
git commit -m "feat(frontend): usePlayer hook (WebSocket + WebAudio)"
```

---

## Task 7: MiniWave Component

**Files:**
- Create: `frontend/src/components/MiniWave.tsx`

- [ ] **Step 1: Create `frontend/src/components/MiniWave.tsx`**

Renders an energy_curve string (digits 0–9, one per bar) as a 40-column sparkline.

```tsx
interface Props {
  curve: string;
  active?: boolean;
  width?: number;
  height?: number;
}

export default function MiniWave({ curve, active = false, width = 80, height = 22 }: Props) {
  const BARS = 40;
  const samples: number[] = [];
  for (let i = 0; i < BARS; i++) {
    const idx = Math.min(curve.length - 1, Math.floor(i * curve.length / BARS));
    samples.push((parseInt(curve[idx] ?? '5', 10) || 5) / 9);
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-end', gap: 1,
      width, height, flexShrink: 0, overflow: 'hidden',
    }}>
      {samples.map((h, i) => (
        <div
          key={i}
          style={{
            flex: 1,
            minWidth: 1,
            height: `${Math.max(15, h * 100)}%`,
            background: active ? 'var(--orange)' : 'var(--text-3)',
            borderRadius: '1px 1px 0 0',
          }}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/MiniWave.tsx
git commit -m "feat(frontend): MiniWave sparkline component"
```

---

## Task 8: ReasoningReveal Component

**Files:**
- Create: `frontend/src/components/ReasoningReveal.tsx`

Shown in Deck B while Claude is working. Shows a pulsing badge during analyzing/planning, then typewriter-reveals Claude's reasoning text once the script is available.

- [ ] **Step 1: Create `frontend/src/components/ReasoningReveal.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';

interface Props {
  status: string;       // deck_b.status: 'analyzing' | 'planning' | 'loading' | 'ready'
  sessionId: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  starting:  'Starting…',
  analyzing: 'Analyzing track…',
  planning:  'Planning transition…',
  loading:   'Loading audio…',
};

export default function ReasoningReveal({ status, sessionId }: Props) {
  const [fullText,   setFullText]   = useState('');
  const [displayed,  setDisplayed]  = useState('');
  const [fetchedFor, setFetchedFor] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const posRef   = useRef(0);

  // Fetch script.reasoning once session is ready
  useEffect(() => {
    if (status !== 'ready' || !sessionId || fetchedFor === sessionId) return;
    setFetchedFor(sessionId);
    apiFetch(`/api/script/${sessionId}`)
      .then(r => r.json())
      .then((s: { reasoning?: string }) => { if (s.reasoning) setFullText(s.reasoning); })
      .catch(() => {});
  }, [status, sessionId, fetchedFor]);

  // Typewriter reveal when fullText arrives
  useEffect(() => {
    if (!fullText) return;
    posRef.current = 0;
    setDisplayed('');
    clearInterval(timerRef.current!);
    timerRef.current = setInterval(() => {
      posRef.current += 2;
      setDisplayed(fullText.slice(0, posRef.current));
      if (posRef.current >= fullText.length) clearInterval(timerRef.current!);
    }, 40);
    return () => clearInterval(timerRef.current!);
  }, [fullText]);

  // Reset when deck_b cycles to a new track
  useEffect(() => {
    if (status === 'analyzing' || status === 'starting') {
      setFullText('');
      setDisplayed('');
      setFetchedFor(null);
      posRef.current = 0;
    }
  }, [status]);

  const label = STATUS_LABELS[status];
  const isWorking = label !== undefined && !displayed;

  if (!isWorking && !displayed) return null;

  return (
    <div style={{ marginTop: 8 }}>
      {isWorking && (
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '.1em',
          padding: '2px 7px',
          borderRadius: 3,
          background: 'rgba(191,90,242,0.12)',
          color: 'var(--purple)',
          animation: 'pulse 1.8s ease-in-out infinite',
        }}>
          {label}
        </span>
      )}
      {displayed && (
        <p style={{
          fontSize: 11,
          color: 'var(--text-2)',
          lineHeight: 1.65,
          fontFamily: 'var(--font-ui)',
        }}>
          {displayed}
          {displayed.length < fullText.length && (
            <span style={{
              display: 'inline-block',
              width: 6, height: 10,
              background: 'var(--purple)',
              verticalAlign: 'middle',
              marginLeft: 2,
              animation: 'blink 1s step-end infinite',
            }} />
          )}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ReasoningReveal.tsx
git commit -m "feat(frontend): ReasoningReveal typewriter component"
```

---

## Task 9: DeckPanel + DeckRow

**Files:**
- Create: `frontend/src/components/DeckPanel.tsx`
- Create: `frontend/src/components/DeckRow.tsx`

- [ ] **Step 1: Create `frontend/src/components/DeckPanel.tsx`**

```tsx
import ReasoningReveal from './ReasoningReveal';
import type { DjDeck, DjDeckB, LibraryTrack } from '../types';

interface Props {
  variant:   'a' | 'b';
  deck:      DjDeck | DjDeckB | null;
  sessionId: string | null;
  track:     LibraryTrack | undefined;
}

function isDeckA(d: DjDeck | DjDeckB | null): d is DjDeck {
  return d !== null && 'hash' in d;
}

export default function DeckPanel({ variant, deck, sessionId, track }: Props) {
  const isA      = variant === 'a';
  const accent   = isA ? 'var(--orange)' : 'var(--blue)';
  const accentLo = isA ? 'var(--orange-lo)' : 'var(--blue-lo)';

  const title    = deck?.title ?? null;
  const deckBStatus = !isA ? ((deck as DjDeckB | null)?.status ?? '') : '';
  const isReady  = isA || deckBStatus === 'ready';

  const energy = track?.energy;
  const energyBar = energy !== undefined
    ? '█'.repeat(energy) + '░'.repeat(Math.max(0, 9 - energy))
    : null;

  return (
    <div style={{
      flex: 1,
      padding: '12px 16px',
      background: deck ? accentLo : 'transparent',
      borderRight: isA ? '1px solid var(--border)' : 'none',
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Label */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '.14em',
        color: deck ? accent : 'var(--text-3)',
        textTransform: 'uppercase',
        marginBottom: 4,
      }}>
        {isA ? 'DECK A' : 'DECK B'}
        {deck && !isA && (
          <span style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>
            · {deckBStatus.toUpperCase()}
          </span>
        )}
        {deck && isA && (
          <span style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>· PLAYING</span>
        )}
      </div>

      {/* Title */}
      <div style={{
        fontSize: 14,
        fontWeight: 600,
        color: isReady ? 'var(--text)' : 'var(--text-3)',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        marginBottom: 4,
      }}>
        {title ?? (isA ? 'No track loaded' : '—')}
      </div>

      {/* Meta row */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        display: 'flex',
        gap: 10,
        alignItems: 'center',
      }}>
        {track?.bpm !== undefined && (
          <span style={{ color: accent }}>{track.bpm.toFixed(0)} BPM</span>
        )}
        {track?.key_camelot && (
          <span style={{ color: 'var(--green)' }}>{track.key_camelot}</span>
        )}
        {energyBar && (
          <span style={{ color: 'var(--text-3)', letterSpacing: 1 }}>{energyBar}</span>
        )}
      </div>

      {/* Reasoning reveal for deck B */}
      {!isA && (
        <ReasoningReveal status={deckBStatus} sessionId={sessionId} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/DeckRow.tsx`**

```tsx
import DeckPanel from './DeckPanel';
import type { DjDeck, DjDeckB, LibraryTrack } from '../types';

interface Props {
  deckA:      DjDeck | null;
  deckB:      DjDeckB | null;
  sessionId:  string | null;
  trackByHash:  (hash: string) => LibraryTrack | undefined;
  trackByTitle: (title: string) => LibraryTrack | undefined;
}

export default function DeckRow({ deckA, deckB, sessionId, trackByHash, trackByTitle }: Props) {
  const trackA = deckA ? trackByHash(deckA.hash) : undefined;
  // deck_b has no hash from the API — use title-based lookup as best-effort
  const trackB = deckB ? trackByTitle(deckB.title) : undefined;

  return (
    <div style={{
      display: 'flex',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      <DeckPanel variant="a" deck={deckA} sessionId={sessionId} track={trackA} />
      <DeckPanel variant="b" deck={deckB} sessionId={sessionId} track={trackB} />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DeckPanel.tsx frontend/src/components/DeckRow.tsx
git commit -m "feat(frontend): DeckPanel and DeckRow components"
```

---

## Task 10: WaveformStrip

**Files:**
- Create: `frontend/src/components/WaveformStrip.tsx`

Single canvas. Renders Deck A energy curve (orange, fades after playhead) + Deck B energy curve (blue, builds in from transition point) + cue point ticks + playhead line.

- [ ] **Step 1: Create `frontend/src/components/WaveformStrip.tsx`**

```tsx
import { useEffect, useRef } from 'react';
import type { CuePoint, LibraryTrack } from '../types';

interface Props {
  trackA:     LibraryTrack | undefined;
  trackB:     LibraryTrack | undefined;
  currentBar: number;
  onSeek:     (bar: number) => void;
}

function sampleCurve(curve: string, targetBars: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < targetBars; i++) {
    const idx = Math.floor(i * curve.length / targetBars);
    out.push((parseInt(curve[idx] ?? '5', 10) || 5) / 9);
  }
  return out;
}

function drawCurve(
  ctx: CanvasRenderingContext2D,
  samples: number[],
  W: number,
  H: number,
  startX: number,
  endX: number,
  colorFrom: string,
  colorTo: string,
  alphaScale: number,
) {
  if (samples.length === 0) return;
  ctx.beginPath();
  ctx.moveTo(startX, H);
  for (let i = 0; i < samples.length; i++) {
    const x = startX + (i / samples.length) * (endX - startX);
    const y = H - samples[i] * (H - 10) - 5;
    ctx.lineTo(x, y);
  }
  ctx.lineTo(endX, H);
  ctx.closePath();
  const grad = ctx.createLinearGradient(startX, 0, endX, 0);
  grad.addColorStop(0, colorFrom);
  grad.addColorStop(1, colorTo);
  ctx.fillStyle = grad;
  ctx.globalAlpha = alphaScale;
  ctx.fill();
  ctx.globalAlpha = 1;
}

export default function WaveformStrip({ trackA, trackB, currentBar, onSeek }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const W = container.clientWidth;
    const H = 64;
    canvas.width  = W;
    canvas.height = H;

    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, W, H);

    const totalBars  = trackA ? Math.max(1, trackA.energy_curve.length) : 128;
    const barWidth   = W / totalBars;
    const playheadX  = (currentBar / totalBars) * W;
    // Estimate transition start at 75% of total bars (visual approximation)
    const transX     = W * 0.75;

    // ── Deck A curve ────────────────────────────────────────────────────────
    if (trackA?.energy_curve) {
      const samplesA = sampleCurve(trackA.energy_curve, totalBars);
      // Past portion (dimmed)
      const pastSamples = samplesA.slice(0, currentBar);
      drawCurve(ctx, pastSamples, W, H, 0, playheadX,
        'rgba(255,95,0,0.15)', 'rgba(255,95,0,0.15)', 1);
      // Future portion (bright)
      const futureSamples = samplesA.slice(currentBar);
      drawCurve(ctx, futureSamples, W, H, playheadX, W,
        'rgba(255,95,0,0.85)', 'rgba(255,95,0,0.2)', 1);
    }

    // ── Deck B curve (transition zone) ──────────────────────────────────────
    if (trackB?.energy_curve && transX < W) {
      const bBars    = Math.max(1, Math.floor(totalBars * 0.25));
      const samplesB = sampleCurve(trackB.energy_curve, bBars);
      drawCurve(ctx, samplesB, W, H, transX, W,
        'rgba(0,180,255,0.05)', 'rgba(0,180,255,0.7)', 1);
    }

    // ── Transition zone dashed line ──────────────────────────────────────────
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(transX, 4);
    ctx.lineTo(transX, H - 4);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Cue points ───────────────────────────────────────────────────────────
    if (trackA?.cue_points) {
      trackA.cue_points.forEach((cp: CuePoint) => {
        const x = (cp.bar / totalBars) * W;
        ctx.fillStyle = 'var(--yellow)';
        // small downward triangle at top
        ctx.beginPath();
        ctx.moveTo(x - 4, 0);
        ctx.lineTo(x + 4, 0);
        ctx.lineTo(x,     6);
        ctx.closePath();
        ctx.fillStyle = '#ffd60a';
        ctx.fill();
      });
    }

    // ── Playhead ─────────────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(playheadX, 0);
    ctx.lineTo(playheadX, H);
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }, [trackA, trackB, currentBar]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x    = e.clientX - rect.left;
    const totalBars = trackA ? Math.max(1, trackA.energy_curve.length) : 128;
    const bar  = Math.round((x / rect.width) * totalBars);
    onSeek(Math.max(0, Math.min(bar, totalBars - 1)));
  };

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: 64,
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        cursor: 'crosshair',
        flexShrink: 0,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%' }}
        onClick={handleClick}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/WaveformStrip.tsx
git commit -m "feat(frontend): WaveformStrip canvas A+B overlay"
```

---

## Task 11: TransportBar

**Files:**
- Create: `frontend/src/components/TransportBar.tsx`

- [ ] **Step 1: Create `frontend/src/components/TransportBar.tsx`**

```tsx
import type { PlayerState } from '../types';

interface Props {
  playerState:     PlayerState;
  currentBar:      number;
  totalBars:       number;
  bufferDepthBars: number;
  onSeek:          (bar: number) => void;
  onStop:          () => void;
}

const STATE_LABELS: Record<PlayerState, string> = {
  idle:       '○',
  connecting: '◌',
  buffering:  '⋯',
  playing:    '▶',
  stopped:    '■',
  error:      '!',
};

export default function TransportBar({
  playerState,
  currentBar,
  totalBars,
  bufferDepthBars,
  onSeek,
  onStop,
}: Props) {
  const pct       = totalBars > 0 ? currentBar / totalBars : 0;
  const bufferPct = totalBars > 0 ? Math.min(1, bufferDepthBars / totalBars) : 0;

  return (
    <div style={{
      height: 44,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '0 16px',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {/* State indicator */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 14,
        color: playerState === 'playing' ? 'var(--orange)'
             : playerState === 'error'   ? 'var(--red)'
             : 'var(--text-3)',
        width: 16,
        textAlign: 'center',
        flexShrink: 0,
      }}>
        {STATE_LABELS[playerState]}
      </span>

      {/* Bar counter */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--text-3)',
        width: 64,
        flexShrink: 0,
      }}>
        {String(currentBar).padStart(3, ' ')} / {totalBars}
      </span>

      {/* Seek bar */}
      <div
        style={{
          flex: 1,
          height: 4,
          background: 'var(--border)',
          borderRadius: 2,
          position: 'relative',
          cursor: 'pointer',
        }}
        onClick={(e) => {
          const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          const bar  = Math.round(((e.clientX - rect.left) / rect.width) * totalBars);
          onSeek(Math.max(0, Math.min(bar, totalBars - 1)));
        }}
      >
        {/* Buffer indicator */}
        <div style={{
          position: 'absolute',
          left: 0, top: 0,
          height: '100%',
          width: `${bufferPct * 100}%`,
          background: 'var(--border2)',
          borderRadius: 2,
        }} />
        {/* Playhead */}
        <div style={{
          position: 'absolute',
          left: 0, top: 0,
          height: '100%',
          width: `${pct * 100}%`,
          background: 'var(--orange)',
          borderRadius: 2,
        }} />
      </div>

      {/* Stop button */}
      {playerState !== 'idle' && playerState !== 'stopped' && (
        <button
          onClick={onStop}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '.1em',
            padding: '3px 10px',
            borderRadius: 3,
            background: 'var(--surface2)',
            color: 'var(--text-2)',
            border: '1px solid var(--border2)',
          }}
        >
          STOP
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TransportBar.tsx
git commit -m "feat(frontend): TransportBar component"
```

---

## Task 12: TrackRow + TrackList + QueueStrip

**Files:**
- Create: `frontend/src/components/TrackRow.tsx`
- Create: `frontend/src/components/TrackList.tsx`
- Create: `frontend/src/components/QueueStrip.tsx`

- [ ] **Step 1: Create `frontend/src/components/TrackRow.tsx`**

```tsx
import MiniWave from './MiniWave';
import type { LibraryTrack } from '../types';

interface Props {
  track:     LibraryTrack;
  isPlaying: boolean;
  isQueued:  boolean;
  onEnqueue: (hash: string) => void;
}

function formatDuration(s: number): string {
  return `${Math.floor(s / 60)}:${Math.round(s % 60).toString().padStart(2, '0')}`;
}

export default function TrackRow({ track, isPlaying, isQueued, onEnqueue }: Props) {
  const title = track.title || track.path.split('/').pop()?.replace(/\.[^.]+$/, '') || '—';

  return (
    <div
      onDoubleClick={() => onEnqueue(track.hash)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 10px',
        borderBottom: '1px solid var(--border)',
        background: isPlaying ? 'var(--orange-lo)' : 'transparent',
        cursor: 'default',
        transition: 'background .1s',
      }}
      onMouseEnter={e => { if (!isPlaying) (e.currentTarget as HTMLDivElement).style.background = 'var(--surface2)'; }}
      onMouseLeave={e => { if (!isPlaying) (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
    >
      {/* Playing indicator */}
      <div style={{
        width: 10, fontSize: 8,
        color: 'var(--orange)', flexShrink: 0, textAlign: 'center',
      }}>
        {isPlaying ? '▶' : ''}
      </div>

      {/* Title + artist */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 500,
          color: isQueued ? 'var(--blue)' : 'var(--text)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {title}
        </div>
        <div style={{
          fontSize: 10, color: 'var(--text-3)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {track.artist || '—'}
        </div>
      </div>

      {/* Mini waveform */}
      <MiniWave curve={track.energy_curve} active={isPlaying} />

      {/* BPM / key / duration */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1, flexShrink: 0,
      }}>
        <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{track.bpm.toFixed(0)}</span>
        <span style={{ fontSize: 10, color: 'var(--green)' }}>{track.key_camelot}</span>
        <span style={{ fontSize: 9,  color: 'var(--text-3)' }}>{formatDuration(track.duration_s)}</span>
      </div>

      {/* Enqueue button */}
      <button
        onClick={() => onEnqueue(track.hash)}
        style={{
          width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
          background: isQueued ? 'var(--blue-lo)' : 'var(--surface2)',
          border: `1px solid ${isQueued ? 'var(--blue)' : 'var(--border2)'}`,
          color: isQueued ? 'var(--blue)' : 'var(--text-2)',
          fontSize: 13, lineHeight: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        title={isQueued ? 'Queued' : 'Add to queue'}
      >
        {isQueued ? '✓' : '+'}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/TrackList.tsx`**

```tsx
import TrackRow from './TrackRow';
import type { LibraryTrack } from '../types';

interface Props {
  tracks:       LibraryTrack[];
  playingHash:  string | null;
  queuedHashes: string[];
  filter:       string;
  onEnqueue:    (hash: string) => void;
}

export default function TrackList({ tracks, playingHash, queuedHashes, filter, onEnqueue }: Props) {
  const filtered = filter
    ? tracks.filter(t =>
        t.title.toLowerCase().includes(filter.toLowerCase()) ||
        t.artist.toLowerCase().includes(filter.toLowerCase()) ||
        t.key_camelot.toLowerCase().includes(filter.toLowerCase()),
      )
    : tracks;

  if (filtered.length === 0) {
    return (
      <div style={{
        padding: '32px 20px', textAlign: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color: 'var(--text-3)', letterSpacing: '.04em',
      }}>
        {tracks.length === 0 ? 'Scan a folder to add tracks' : 'No tracks match the filter'}
      </div>
    );
  }

  return (
    <div style={{ overflowY: 'auto', flex: 1 }}>
      {filtered.map(t => (
        <TrackRow
          key={t.hash}
          track={t}
          isPlaying={t.hash === playingHash}
          isQueued={queuedHashes.includes(t.hash)}
          onEnqueue={onEnqueue}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/QueueStrip.tsx`**

```tsx
import type { LibraryTrack } from '../types';

interface Props {
  queuedHashes: string[];
  trackByHash:  (hash: string) => LibraryTrack | undefined;
}

export default function QueueStrip({ queuedHashes, trackByHash }: Props) {
  if (queuedHashes.length === 0) return null;

  return (
    <div style={{
      display: 'flex',
      gap: 6,
      padding: '6px 10px',
      overflowX: 'auto',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {queuedHashes.map((hash, i) => {
        const t = trackByHash(hash);
        return (
          <div
            key={hash}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 8px', borderRadius: 3,
              background: 'var(--blue-lo)',
              border: '1px solid rgba(0,180,255,0.2)',
              flexShrink: 0,
            }}
          >
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--blue)', marginRight: 2,
            }}>
              {i + 1}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
              {t?.title ?? hash.slice(0, 8)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TrackRow.tsx frontend/src/components/TrackList.tsx frontend/src/components/QueueStrip.tsx
git commit -m "feat(frontend): TrackRow, TrackList, QueueStrip"
```

---

## Task 13: LibraryDrawer

**Files:**
- Create: `frontend/src/components/LibraryDrawer.tsx`

- [ ] **Step 1: Create `frontend/src/components/LibraryDrawer.tsx`**

```tsx
import { useState } from 'react';
import QueueStrip from './QueueStrip';
import TrackList from './TrackList';
import type { LibraryScanJob, LibraryTrack } from '../types';

interface Props {
  tracks:       LibraryTrack[];
  scanJob:      LibraryScanJob | null;
  playingHash:  string | null;
  queuedHashes: string[];
  open:         boolean;
  onToggle:     () => void;
  onScan:       () => void;
  onEnqueue:    (hash: string) => void;
  trackByHash:  (hash: string) => LibraryTrack | undefined;
}

export default function LibraryDrawer({
  tracks, scanJob, playingHash, queuedHashes,
  open, onToggle, onScan, onEnqueue, trackByHash,
}: Props) {
  const [filter, setFilter] = useState('');
  const scanning = scanJob?.status === 'running';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface)',
      borderTop: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      {/* Tab / header */}
      <div
        onClick={onToggle}
        style={{
          height: 32,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 12px',
          cursor: 'pointer',
          borderBottom: open ? '1px solid var(--border)' : 'none',
          flexShrink: 0,
          userSelect: 'none',
        }}
      >
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '.14em',
          color: 'var(--text-3)',
          textTransform: 'uppercase',
        }}>
          {open ? '▾' : '▸'} LIBRARY
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-3)',
          background: 'var(--surface2)',
          padding: '1px 6px',
          borderRadius: 3,
        }}>
          {tracks.length}
        </span>

        <div style={{ flex: 1 }} />

        {/* Scan progress inline */}
        {scanning && scanJob && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)' }}>
            {scanJob.progress} / {scanJob.total}
          </span>
        )}

        <button
          onClick={(e) => { e.stopPropagation(); onScan(); }}
          disabled={scanning}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            padding: '2px 10px',
            borderRadius: 3,
            background: 'var(--surface2)',
            color: 'var(--text-2)',
            border: '1px solid var(--border2)',
            opacity: scanning ? 0.4 : 1,
            cursor: scanning ? 'not-allowed' : 'pointer',
          }}
        >
          {scanning ? 'Scanning…' : 'Scan Folder'}
        </button>
      </div>

      {/* Drawer content */}
      {open && (
        <>
          {/* Scan result bar */}
          {scanJob && scanJob.status !== 'running' && (
            <div style={{
              padding: '4px 12px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: scanJob.status === 'error' ? 'var(--red)' : 'var(--text-3)',
              borderBottom: '1px solid var(--border)',
              flexShrink: 0,
            }}>
              {scanJob.status === 'error'
                ? scanJob.error
                : `Done · ${scanJob.new} new, ${scanJob.known} cached`}
            </div>
          )}

          {/* Search */}
          <div style={{ padding: '6px 10px', flexShrink: 0 }}>
            <input
              style={{ width: '100%', fontSize: 12 }}
              placeholder="Filter by title, artist, key…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
            />
          </div>

          {/* Column headers */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '3px 10px',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            <div style={{ width: 10 }} />
            <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', letterSpacing: '.1em' }}>TRACK</span>
            <span style={{ width: 80, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)' }}>WAVE</span>
            <span style={{ width: 54, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', textAlign: 'right' }}>BPM / KEY</span>
            <div style={{ width: 30 }} />
          </div>

          {/* Queue strip */}
          <QueueStrip queuedHashes={queuedHashes} trackByHash={trackByHash} />

          {/* Track list */}
          <TrackList
            tracks={tracks}
            playingHash={playingHash}
            queuedHashes={queuedHashes}
            filter={filter}
            onEnqueue={onEnqueue}
          />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/LibraryDrawer.tsx
git commit -m "feat(frontend): LibraryDrawer with scan, search, queue"
```

---

## Task 14: TopBar

**Files:**
- Create: `frontend/src/components/TopBar.tsx`

- [ ] **Step 1: Create `frontend/src/components/TopBar.tsx`**

```tsx
import type { DjStartOpts } from '../types';

const MODELS = [
  { id: 'claude-sonnet-4-6',         label: 'Sonnet 4.6' },
  { id: 'claude-opus-4-7',           label: 'Opus 4.7'   },
  { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5'  },
];

interface Props {
  isActive:      boolean;
  refBpm:        number | null;
  model:         string;
  claudePick:    boolean;
  error:         string | null;
  onStart:       (opts: Omit<DjStartOpts, 'pool' | 'queue'>) => void;
  onStop:        () => void;
  onModelChange: (model: string) => void;
  onClaudePickChange: (v: boolean) => void;
}

export default function TopBar({
  isActive, refBpm, model, claudePick, error,
  onStart, onStop, onModelChange, onClaudePickChange,
}: Props) {
  return (
    <div style={{
      height: 32,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '0 14px',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {/* Brand */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '.2em',
        color: 'var(--orange)',
      }}>
        CLAUDE DJ
      </span>

      {/* BPM */}
      {refBpm && (
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          fontWeight: 600,
          color: 'var(--text)',
        }}>
          {refBpm.toFixed(1)}
          <span style={{ fontSize: 9, color: 'var(--text-3)', marginLeft: 3 }}>BPM</span>
        </span>
      )}

      <div style={{ flex: 1 }} />

      {/* Error */}
      {error && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--red)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {error}
        </span>
      )}

      {/* Claude pick toggle */}
      {!isActive && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={claudePick}
            onChange={e => onClaudePickChange(e.target.checked)}
            style={{ width: 12, height: 12, accentColor: 'var(--orange)' }}
          />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', letterSpacing: '.08em' }}>
            CLAUDE PICKS
          </span>
        </label>
      )}

      {/* Model selector */}
      {!isActive && (
        <select
          value={model}
          onChange={e => onModelChange(e.target.value)}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            padding: '2px 6px',
            background: 'var(--surface2)',
            border: '1px solid var(--border2)',
            color: 'var(--text-2)',
          }}
        >
          {MODELS.map(m => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      )}

      {/* Start / Stop */}
      <button
        onClick={() => isActive
          ? onStop()
          : onStart({ let_claude_pick: claudePick, model })
        }
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '.1em',
          padding: '3px 14px',
          borderRadius: 3,
          background: isActive ? 'rgba(255,55,95,0.1)' : 'rgba(255,95,0,0.12)',
          color: isActive ? 'var(--red)' : 'var(--orange)',
          border: `1px solid ${isActive ? 'var(--red)' : 'var(--orange)'}`,
        }}
      >
        {isActive ? 'STOP' : 'START'}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TopBar.tsx
git commit -m "feat(frontend): TopBar with model selector and start/stop"
```

---

## Task 15: App Root — Wire Everything Together

**Files:**
- Create: `frontend/src/App.tsx`

This is the only file that calls hooks. CSS grid layout: `32px 1fr 64px 44px [drawerRows]`. When drawer is open, the `1fr` deck row compresses and the drawer expands.

- [ ] **Step 1: Create `frontend/src/App.tsx`**

```tsx
import { useCallback, useEffect, useState } from 'react';
import TopBar from './components/TopBar';
import DeckRow from './components/DeckRow';
import WaveformStrip from './components/WaveformStrip';
import TransportBar from './components/TransportBar';
import LibraryDrawer from './components/LibraryDrawer';
import { useDjSession } from './hooks/useDjSession';
import { useLibrary } from './hooks/useLibrary';
import { usePlayer } from './hooks/usePlayer';
import type { DjStartOpts } from './types';

const DRAWER_OPEN_KEY = 'claude-dj:drawer-open';

export default function App() {
  const [model,      setModel]      = useState('claude-sonnet-4-6');
  const [claudePick, setClaudePick] = useState(true);
  const [localQueue, setLocalQueue] = useState<string[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(
    () => localStorage.getItem(DRAWER_OPEN_KEY) !== 'false',
  );

  const { tracks, scanJob, scanFolder, trackByHash, trackByTitle } = useLibrary();
  const { djId, djState, error: djError, startDj, stopDj, enqueue } = useDjSession();

  const sessionId  = djState?.session_id ?? null;
  const totalBars  = djState?.deck_a
    ? (trackByHash(djState.deck_a.hash)?.energy_curve.length ?? 128)
    : 128;

  const { playerState, currentBar, bufferDepthBars, seek, stop: stopPlayer } = usePlayer(sessionId);

  // Open drawer automatically if library is empty
  useEffect(() => {
    if (tracks.length === 0) setDrawerOpen(true);
  }, [tracks.length]);

  const toggleDrawer = useCallback(() => {
    setDrawerOpen(v => {
      localStorage.setItem(DRAWER_OPEN_KEY, String(!v));
      return !v;
    });
  }, []);

  const handleScan = useCallback(async () => {
    const folder = await window.electron?.selectFolder() ?? prompt('Folder path to scan:');
    if (folder) scanFolder(folder);
  }, [scanFolder]);

  const handleStart = useCallback((opts: Omit<DjStartOpts, 'pool' | 'queue'>) => {
    startDj({
      ...opts,
      pool:  localQueue.length > 0 ? [] : tracks.map(t => t.hash),
      queue: localQueue,
    });
    setLocalQueue([]);
  }, [startDj, localQueue, tracks]);

  const handleStop = useCallback(() => {
    stopPlayer();
    stopDj();
  }, [stopPlayer, stopDj]);

  const handleEnqueue = useCallback(async (hash: string) => {
    if (djId) {
      await enqueue(hash);
    } else {
      setLocalQueue(q => q.includes(hash) ? q : [...q, hash]);
    }
  }, [djId, enqueue]);

  const handleSeek = useCallback((bar: number) => {
    seek(bar);
  }, [seek]);

  const playingHash  = djState?.deck_a?.hash ?? null;
  const queuedHashes = djState?.queue ?? localQueue;

  const trackA = djState?.deck_a ? trackByHash(djState.deck_a.hash) : undefined;
  const trackB = djState?.deck_b ? trackByTitle(djState.deck_b.title) : undefined;

  return (
    <div style={{
      display: 'grid',
      height: '100vh',
      gridTemplateRows: drawerOpen
        ? '32px 1fr 64px 44px 45vh'
        : '32px 1fr 64px 44px 32px',
      overflow: 'hidden',
      transition: 'grid-template-rows .25s ease',
    }}>
      <TopBar
        isActive={!!djId}
        refBpm={djState?.ref_bpm ?? null}
        model={model}
        claudePick={claudePick}
        error={djError}
        onStart={handleStart}
        onStop={handleStop}
        onModelChange={setModel}
        onClaudePickChange={setClaudePick}
      />

      <DeckRow
        deckA={djState?.deck_a ?? null}
        deckB={djState?.deck_b ?? null}
        sessionId={sessionId}
        trackByHash={trackByHash}
        trackByTitle={trackByTitle}
      />

      <WaveformStrip
        trackA={trackA}
        trackB={trackB}
        currentBar={currentBar}
        onSeek={handleSeek}
      />

      <TransportBar
        playerState={playerState}
        currentBar={currentBar}
        totalBars={totalBars}
        bufferDepthBars={bufferDepthBars}
        onSeek={handleSeek}
        onStop={handleStop}
      />

      <LibraryDrawer
        tracks={tracks}
        scanJob={scanJob}
        playingHash={playingHash}
        queuedHashes={queuedHashes}
        open={drawerOpen}
        onToggle={toggleDrawer}
        onScan={handleScan}
        onEnqueue={handleEnqueue}
        trackByHash={trackByHash}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): App root, grid layout, hook wiring"
```

---

## Task 16: Smoke Test

- [ ] **Step 1: Ensure backend is running**

```bash
cd claude-dj && conda activate claude-dj && uvicorn server:app --port 8000 --reload
```

Expected: `INFO: Application startup complete.`

- [ ] **Step 2: Start Vite dev server**

```bash
cd frontend && npm run dev:vite
```

Expected: `VITE ready in …ms ➜ Local: http://localhost:5173/`

- [ ] **Step 3: Open http://localhost:5173 and verify each zone**

Check in order:

1. **TopBar**: "CLAUDE DJ" in orange, model selector, START button visible
2. **DeckRow**: Two panels, Deck A shows "No track loaded", Deck B shows "—"
3. **WaveformStrip**: Black canvas strip, no errors in console
4. **TransportBar**: `○` state indicator, `0 / 128` bar counter
5. **LibraryDrawer**: Opens by default (no tracks). "Scan Folder" button visible.
6. **Scan folder**: Click Scan Folder → select a folder → watch progress counter → tracks appear in list
7. **Start DJ**: Click START → Deck A shows track title + orange accent → Deck B shows "ANALYZING" badge → eventually "PLANNING" + reasoning text types in
8. **Waveform**: Orange curve appears and playhead advances
9. **Seek**: Click waveform → playhead jumps
10. **Library filter**: Type artist name → list filters correctly

- [ ] **Step 4: Check browser console for errors**

Expected: No React errors, no uncaught exceptions. WebSocket connection established to `/ws/stream/...`.

- [ ] **Step 5: Final commit**

```bash
cd .. && git add -A && git commit -m "feat(frontend): complete rebuild — Geist font, deck layout, A+B waveform, reasoning reveal"
```

---

## Notes

- **`DjDeckB` has no `hash`**: The `/api/dj/{id}` endpoint only exposes `status` and `title` for deck_b. `trackByTitle` is a best-effort lookup; if two library tracks share a title it picks the first. This is a backend limitation, not a frontend bug.
- **CSS grid transition**: `grid-template-rows` is not universally animatable in all browsers. If the transition is janky, remove the `transition` style on the App div — the layout change still works, just without animation.
- **AudioContext autoplay**: Chrome may block `new AudioContext()` until a user gesture. The START button click counts as a gesture — this is fine.
- **`npm run dev` vs `npm run dev:vite`**: Use `dev:vite` alone for browser testing without Electron. Use `dev` to run the full Electron app with the native folder picker.
