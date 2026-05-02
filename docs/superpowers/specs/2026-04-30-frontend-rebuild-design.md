# Claude DJ Frontend Rebuild — Design Spec
_2026-04-30_

## Overview

Full rebuild of the React frontend from scratch. Stack stays the same (React 19, Vite, TypeScript, Electron). All existing source files under `frontend/src/` are deleted; this spec defines the replacement.

The design goal: make the AI brain visible. Every layout and interaction decision prioritises showing what Claude is doing, not hiding it behind spinners.

---

## Design Decisions

| Dimension | Decision | Rationale |
|---|---|---|
| Layout | Deck Center — decks top, library bottom drawer | Familiar DJ-software anchor; library stays out of the way during playback |
| Aesthetic | Warm Analog — true black `#080808`, orange Deck A, blue Deck B | High contrast, energetic, deck identity through color |
| Font | Geist Sans (UI) + Geist Mono (data/metadata) | Clean developer-tool aesthetic, consistent with Claude Code |
| Waveform | A+B Overlay — single canvas strip, both decks | Makes the crossfade zone tangible; the AI's work is visible |
| AI Status | Reasoning Reveal — Claude's text types in when planning completes | Makes Claude feel present and intentional, not like a loading bar |

---

## Color Palette

```
--bg:         #080808   /* true black body */
--surface:    #0e0e0e   /* card/panel backgrounds */
--surface2:   #141414   /* input backgrounds, hover states */
--border:     #1e1e1e
--border2:    #2a2a2a

--orange:     #ff5f00   /* Deck A accent — playing */
--orange-lo:  rgba(255,95,0,0.08)
--blue:       #00b4ff   /* Deck B accent — incoming */
--blue-lo:    rgba(0,180,255,0.08)
--purple:     #bf5af2   /* Claude / AI actions */
--green:      #30d158   /* ready / done states */
--yellow:     #ffd60a   /* cue points */
--red:        #ff375f   /* error */

--text:       #e8e8e8
--text-2:     #666
--text-3:     #333
```

---

## Typography

```css
/* Available via Google Fonts or npm geist */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

--font-ui:   'Geist', system-ui, sans-serif;
--font-mono: 'Geist Mono', ui-monospace, monospace;
```

- UI labels, titles, descriptions → Geist
- BPM, key, bar numbers, timestamps, tag badges → Geist Mono

---

## Layout Grid

```
┌─────────────────────────────────────────────────────┐
│  TOPBAR                                             │  32px fixed
├───────────────────────┬─────────────────────────────┤
│  DECK A               │  DECK B                     │
│  (orange)             │  (blue / purple while AI)   │  ~140px
├───────────────────────┴─────────────────────────────┤
│  WAVEFORM STRIP                                     │  64px fixed
├─────────────────────────────────────────────────────┤
│  TRANSPORT BAR                                      │  44px fixed
├─────────────────────────────────────────────────────┤
│  LIBRARY DRAWER  (tab: 32px collapsed, ~40% open)   │  flex 1
└─────────────────────────────────────────────────────┘
```

Total layout is `100vh`, no scroll. Library drawer slides up over the transport area.

---

## Component Hierarchy

```
App
├── TopBar
│   ├── Brand ("CLAUDE DJ" — Geist Mono, orange)
│   ├── BpmDisplay (ref_bpm, pulses on beat)
│   ├── ModelSelector (Sonnet / Opus / Haiku dropdown)
│   ├── ClaudePickToggle (let Claude choose next track)
│   └── DjStartStop (Start button → Stop when active)
│
├── DeckRow
│   ├── DeckPanel [variant=a]
│   │   ├── DeckLabel ("DECK A · PLAYING")
│   │   ├── TrackTitle + Artist
│   │   └── DeckMeta (BPM · key_camelot · energy bar)
│   └── DeckPanel [variant=b]
│       ├── DeckLabel ("DECK B · {status}")
│       ├── TrackTitle (dimmed until ready)
│       ├── DeckMeta
│       └── ReasoningReveal  ← shown while status = planning/loading
│
├── WaveformStrip  (single <canvas>)
│   — renders both decks' energy_curve overlaid
│   — orange = Deck A (left→playhead), blue = Deck B (transition zone→right)
│   — white playhead line advances via current_bar polling
│   — yellow tick marks at cue_points
│   — click to seek (sends {action:"seek",bar:N} over WebSocket)
│
├── TransportBar
│   ├── PlayStopButton
│   ├── SeekBar (mirrors WaveformStrip position, redundant control)
│   └── BufferDepthIndicator (buffer_depth_bars as small fill bar)
│
└── LibraryDrawer
    ├── DrawerTab (always visible, click or drag to open/close)
    ├── LibraryHeader
    │   ├── ScanButton (opens Electron folder picker or prompt())
    │   ├── TrackCount badge
    │   └── SearchInput (filters title / artist / key)
    ├── QueueStrip (horizontal scrollable row of queued track pills)
    └── TrackList
        └── TrackRow ×N
            ├── PlayingIndicator (▶ when hash === deck_a.hash)
            ├── TrackInfo (title + artist)
            ├── MiniWave (energy_curve → 40-bar sparkline, orange if playing)
            ├── TrackMeta (BPM · key_camelot · duration)
            └── EnqueueButton (+ / ✓)
```

---

## File Structure

```
frontend/src/
├── main.tsx
├── App.tsx
├── index.css          (CSS variables + resets only)
├── api.ts             (apiFetch helper, WS connection)
├── types.ts           (LibraryTrack, DjState, DjDeck, MixScript, etc.)
├── hooks/
│   ├── useDjSession.ts    (polling /api/dj/{id}, manages djState)
│   ├── usePlayer.ts       (WebSocket + WebAudio, play/stop/seek)
│   └── useLibrary.ts      (fetch /api/library, scan, filter)
└── components/
    ├── TopBar.tsx
    ├── DeckRow.tsx
    ├── DeckPanel.tsx
    ├── ReasoningReveal.tsx
    ├── WaveformStrip.tsx
    ├── TransportBar.tsx
    ├── LibraryDrawer.tsx
    ├── TrackList.tsx
    ├── TrackRow.tsx
    ├── MiniWave.tsx
    └── QueueStrip.tsx
```

---

## Key Behaviours

### ReasoningReveal

- Shown on Deck B when `deck_b.status` is `"analyzing"`, `"planning"`, or `"loading"`
- While `"analyzing"` or `"planning"`: shows animated status text (`"Analyzing track…"`, `"Planning transition…"`) with a purple pulsing badge
- When `deck_b.status` becomes `"ready"` and `session.script` is available: fetches `GET /api/script/{session_id}`, extracts `script.reasoning`, then plays it back via a CSS typewriter animation (not streaming — data already available, just revealed progressively at ~30 chars/sec)
- Fades out when deck B transitions to Deck A (becomes "Playing")

### WaveformStrip

- Single `<canvas>` spanning full width, 64px tall
- Re-renders on: `current_bar` change (polled every 500ms from `/api/status/{id}`), new session load, library track change
- Energy curves sourced from `_library[hash].energy_curve` (looked up by `deck_a.hash` / `deck_b.hash`); falls back to flat line if hash not yet in library
- Draw order:
  1. Deck A energy curve — orange filled gradient, left edge to playhead (full opacity), playhead to transition start (25% opacity)
  2. Deck B energy curve — blue filled gradient, transition start to right edge, opacity grows as transition approaches
  3. Transition zone — dashed vertical line where crossfade begins
  4. Cue point ticks — yellow `▼` marks above the strip
  5. Playhead — white 2px vertical line at `current_bar / total_bars * width`
- Click handler: converts x-position to bar number, sends seek command via WebSocket

### LibraryDrawer

- Collapsed by default — shows a 32px tab at bottom of screen ("LIBRARY · {n} tracks")
- Opens on click; expands upward, pushing deck/waveform area up via CSS grid row resizing (does not overlay — layout reflows)
- Open/closed state persisted in `localStorage`
- When open: takes up to 45% of viewport height; DeckRow + Waveform compress proportionally via CSS grid `fr` units
- Scan triggers Electron IPC `openFolder` if available, falls back to `prompt()`
- Track rows: double-click or `+` button enqueues; if DJ session active, also calls `POST /api/dj/{id}/queue`

### useDjSession hook

- Polls `GET /api/dj/{dj_id}` every 1500ms while session active
- Exposes: `djState`, `sessionId`, `startDj(opts)`, `stopDj()`
- On `status === "error"`: stops polling, surfaces error

### usePlayer hook

- Manages WebSocket connection to `/ws/stream/{session_id}`
- WebAudio: `AudioContext` → `ScriptProcessorNode` (or `AudioWorkletNode`) consuming float32 PCM chunks
- Handles `{type:"loading"}` frames by showing buffer progress
- Handles `{type:"end"}` by transitioning to stopped state
- Exposes: `play()`, `stop()`, `seek(bar)`, `currentBar`, `bufferDepthBars`, `playerState`

---

## Interaction Flows

### Cold start
1. App opens → library fetched → if empty, drawer opens automatically
2. Scan folder → progress bar in drawer header → library populates
3. User queues tracks (or leaves it to Claude) → clicks Start
4. Deck A begins loading, Deck B shows "Analyzing…" immediately

### Live transition
1. ~16 bars before end of Deck A: Deck B status → `"planning"` → ReasoningReveal animates in
2. Status → `"loading"` → reasoning text types in (from script.reasoning)
3. Status → `"ready"` → Deck B track info becomes full brightness, waveform strip shows blue incoming curve
4. Crossfade plays — waveform strip orange fades, blue grows
5. Deck A fades out, Deck B becomes the new Deck A; a new Deck B planning cycle begins immediately

### Seek
- Click anywhere on WaveformStrip or drag SeekBar
- `usePlayer.seek(bar)` sends `{action:"seek",bar}` over WebSocket
- `currentBar` updates on next status poll

---

## Electron Integration

`electron/preload.cjs` already exposes `window.electronAPI.openFolder()`. Library scan uses it. No other Electron-specific features needed for this build.

---

## What's Explicitly Out of Scope

- EQ / FX controls (auto-DJ handles it server-side)
- Manual beatmatching or crossfader
- Waveform zoom
- Multiple simultaneous DJ sessions
- Track editing or metadata editing
