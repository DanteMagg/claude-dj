import { useCallback, useEffect, useRef, useState } from "react";
import ClawdDJ from "./ClawdDJ";
import { usePlayer } from "../hooks/usePlayer";
import { barToMmss } from "../utils";
import type { DjState, MixAction, MixScript, TrackRef } from "../types";

// ── helpers ───────────────────────────────────────────────────────────────────

function seededBars(seed: string, count: number): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (Math.imul(31, h) + seed.charCodeAt(i)) | 0;
  return Array.from({ length: count }, () => {
    h ^= h << 13; h ^= h >> 17; h ^= h << 5;
    return 0.15 + (((h >>> 0) / 0xffffffff) * 0.85);
  });
}

function estimateTotalBars(script: MixScript): number {
  let max = 0;
  for (const a of script.actions) {
    const b = (a.at_bar ?? a.start_bar ?? a.bar ?? 0) + (a.duration_bars ?? 0);
    if (b > max) max = b;
  }
  return max + 32;
}

function actionBar(a: MixAction) { return a.at_bar ?? a.start_bar ?? a.bar ?? 0; }

const ACTION_COLOR: Record<string, string> = {
  play:      "#444",
  fade_in:   "#00b4ff",
  fade_out:  "#ff5f00",
  bass_swap: "#ff375f",
  loop:      "#bf5af2",
  eq:        "#ffd60a",
};

function trackFileName(track: TrackRef): string {
  return track.path.split("/").pop()?.replace(/\.[^.]+$/, "") ?? track.id;
}

// ── Waveform ──────────────────────────────────────────────────────────────────

function Waveform({
  script, totalBars, currentBar, bufferBars, onSeek,
}: {
  script: MixScript; totalBars: number; currentBar: number;
  bufferBars: number; onSeek: (bar: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const NUM_BARS = 220;
  const bars = seededBars(script.tracks.map((t) => t.id).join(""), NUM_BARS);

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!ref.current) return;
    const { left, width } = ref.current.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - left) / width));
    const bar  = Math.round((frac * totalBars) / 8) * 8;
    onSeek(bar);
  }, [totalBars, onSeek]);

  const playheadPct  = totalBars > 0 ? (currentBar / totalBars) * 100 : 0;
  const bufferEndPct = totalBars > 0 ? (Math.min(totalBars, currentBar + bufferBars) / totalBars) * 100 : 0;

  return (
    <div className="wf-root" ref={ref} onClick={handleClick}>
      {/* bars */}
      <div className="wf-bars">
        {bars.map((h, i) => {
          const barPos = (i / NUM_BARS) * totalBars;
          const past   = barPos < currentBar;
          const buf    = !past && barPos < currentBar + bufferBars;
          return (
            <div
              key={i}
              className="wf-bar"
              style={{
                height: `${h * 100}%`,
                background: past ? "var(--orange)" : buf ? "#3a3a3a" : "#252525",
                opacity: past ? 0.85 : 1,
              }}
            />
          );
        })}
      </div>

      {/* action markers */}
      {script.actions.map((a, i) => {
        const pct = totalBars > 0 ? (actionBar(a) / totalBars) * 100 : 0;
        return (
          <div key={i} className="wf-marker" style={{
            left: `${pct}%`,
            background: ACTION_COLOR[a.type] ?? "#555",
          }} title={`${a.type} · ${a.track} · bar ${actionBar(a)}`} />
        );
      })}

      {/* buffer zone overlay */}
      <div className="wf-buf-zone" style={{
        left: `${playheadPct}%`,
        width: `${Math.max(0, bufferEndPct - playheadPct)}%`,
      }} />

      {/* playhead */}
      <div className="wf-playhead" style={{ left: `${playheadPct}%` }} />

      {/* time labels */}
      <div className="wf-time wf-time-start">{barToMmss(currentBar, script.tracks[0]?.bpm ?? 120)}</div>
      <div className="wf-time wf-time-end">{barToMmss(totalBars, script.tracks[0]?.bpm ?? 120)}</div>

      <style>{`
        .wf-root {
          position: relative; cursor: crosshair; overflow: hidden;
          height: 68px; background: var(--surface); border-top: 1px solid var(--border);
          border-bottom: 1px solid var(--border); user-select: none;
          flex-shrink: 0;
        }
        .wf-bars {
          position: absolute; inset: 8px 0;
          display: flex; align-items: flex-end; gap: 1px; padding: 0 2px;
        }
        .wf-bar { flex: 1; min-width: 1px; border-radius: 1px 1px 0 0; transition: background .1s; }
        .wf-marker {
          position: absolute; top: 0; width: 1px; height: 100%; opacity: 0.75;
          pointer-events: none;
        }
        .wf-buf-zone {
          position: absolute; top: 0; height: 100%;
          background: rgba(255,255,255,.03); pointer-events: none;
        }
        .wf-playhead {
          position: absolute; top: 0; width: 2px; height: 100%;
          background: var(--orange); box-shadow: 0 0 8px var(--orange);
          pointer-events: none; transform: translateX(-50%);
        }
        .wf-time {
          position: absolute; bottom: 3px;
          font-family: var(--mono); font-size: 10px; color: var(--text-2);
          pointer-events: none;
        }
        .wf-time-start { left: 6px; }
        .wf-time-end   { right: 6px; }
      `}</style>
    </div>
  );
}

// ── Deck panel ────────────────────────────────────────────────────────────────

function Deck({
  track, side, currentBar, totalBars, script,
}: {
  track: TrackRef | undefined; side: "A" | "B";
  currentBar: number; totalBars: number; script: MixScript;
}) {
  const isLeft = side === "A";
  const NUM_BARS = 80;
  const bars = seededBars(track?.id ?? side, NUM_BARS);

  // find the fade_in/out bars for this track
  const actions = script.actions.filter((a) => a.track === track?.id);
  const mixIn  = actions.find((a) => a.type === "play" || a.type === "fade_in");
  const mixOut = actions.find((a) => a.type === "fade_out");
  const mixInBar  = mixIn  ? actionBar(mixIn)  : 0;
  const mixOutBar = mixOut ? actionBar(mixOut)  : totalBars;

  // position within this deck's track
  const relBar     = Math.max(0, currentBar - mixInBar);
  const deckLength = Math.max(1, mixOutBar - mixInBar + (mixOut?.duration_bars ?? 0));
  const positionPct = Math.min(1, relBar / deckLength);

  return (
    <div className={`deck deck--${isLeft ? "a" : "b"}`}>
      <div className="deck-header">
        <span className="deck-id">{side}</span>
        <span className="deck-label">DECK {side}</span>
      </div>

      {track ? (
        <>
          <div className="deck-title">{trackFileName(track)}</div>
          <div className="deck-bpm">
            <span className="deck-bpm-val">{track.bpm.toFixed(1)}</span>
            <span className="deck-bpm-unit">BPM</span>
          </div>

          {/* mini waveform */}
          <div className="deck-wf">
            {bars.map((h, i) => {
              const frac = i / NUM_BARS;
              const past = frac < positionPct;
              return (
                <div key={i} className="deck-wf-bar" style={{
                  height: `${h * 100}%`,
                  background: past ? "var(--orange)" : isLeft ? "#2a2a2a" : "#1e2a38",
                }} />
              );
            })}
            <div className="deck-wf-head" style={{ left: `${positionPct * 100}%` }} />
          </div>

          <div className="deck-cues">
            {actions.filter((a) => ["play", "fade_in", "bass_swap", "loop"].includes(a.type)).slice(0, 4).map((a, i) => (
              <div key={i} className="deck-cue" style={{ background: ACTION_COLOR[a.type] ?? "#333" }}>
                <span className="deck-cue-type">{a.type.replace("_", "·").toUpperCase().slice(0, 4)}</span>
                <span className="deck-cue-bar">b{actionBar(a)}</span>
              </div>
            ))}
          </div>

          <div className="deck-meta">
            <span>MIX IN <b>{barToMmss(mixInBar, track.bpm)}</b></span>
            <span>MIX OUT <b>{barToMmss(mixOutBar, track.bpm)}</b></span>
          </div>
        </>
      ) : (
        <div className="deck-empty">NO TRACK</div>
      )}

      <style>{`
        .deck {
          flex: 1; display: flex; flex-direction: column; gap: 10px;
          padding: 14px 16px; min-width: 0;
          background: var(--surface); border: 1px solid var(--border);
        }
        .deck--a { border-right: none; border-radius: var(--radius) 0 0 var(--radius); }
        .deck--b { border-left: none; border-radius: 0 var(--radius) var(--radius) 0; }

        .deck-header {
          display: flex; align-items: center; gap: 8px;
        }
        .deck-id {
          font-family: var(--mono); font-size: 11px; font-weight: 600;
          color: ${isLeft ? "var(--orange)" : "var(--blue)"};
          background: ${isLeft ? "var(--orange-lo)" : "var(--blue-lo)"};
          padding: 2px 7px; border-radius: 3px; letter-spacing: .06em;
        }
        .deck-label {
          font-size: 10px; font-weight: 600; letter-spacing: .12em;
          color: var(--text-2); text-transform: uppercase;
        }
        .deck-title {
          font-size: 14px; font-weight: 600; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; color: var(--text);
        }
        .deck-bpm {
          display: flex; align-items: baseline; gap: 5px;
        }
        .deck-bpm-val {
          font-family: var(--mono); font-size: 28px; font-weight: 600;
          color: ${isLeft ? "var(--orange)" : "var(--blue)"};
          line-height: 1;
        }
        .deck-bpm-unit {
          font-size: 10px; font-weight: 600; letter-spacing: .1em;
          color: var(--text-2); text-transform: uppercase;
        }
        .deck-wf {
          height: 40px; background: var(--surface2); border-radius: 3px;
          position: relative; display: flex; align-items: flex-end;
          gap: 1px; padding: 3px 2px; overflow: hidden;
        }
        .deck-wf-bar { flex: 1; border-radius: 1px 1px 0 0; }
        .deck-wf-head {
          position: absolute; top: 0; bottom: 0; width: 2px;
          background: ${isLeft ? "var(--orange)" : "var(--blue)"};
          transform: translateX(-50%);
          box-shadow: 0 0 4px ${isLeft ? "var(--orange)" : "var(--blue)"};
        }
        .deck-cues {
          display: flex; gap: 4px; flex-wrap: wrap;
        }
        .deck-cue {
          display: flex; flex-direction: column; gap: 1px;
          padding: 4px 6px; border-radius: 3px; opacity: 0.7; min-width: 40px;
        }
        .deck-cue-type {
          font-family: var(--mono); font-size: 8px; font-weight: 600;
          color: white; letter-spacing: .06em;
        }
        .deck-cue-bar {
          font-family: var(--mono); font-size: 9px; color: rgba(255,255,255,.7);
        }
        .deck-meta {
          display: flex; gap: 16px; font-size: 10px; color: var(--text-2);
          font-family: var(--mono); letter-spacing: .04em;
        }
        .deck-meta b { color: var(--text); font-weight: 500; }
        .deck-empty {
          flex: 1; display: flex; align-items: center; justify-content: center;
          font-family: var(--mono); font-size: 11px; color: var(--text-3);
          letter-spacing: .1em;
        }
      `}</style>
    </div>
  );
}

// ── EQ knob (decorative) ──────────────────────────────────────────────────────

function EqKnob({ value = 0.5, label, color = "#555" }: { value?: number; label: string; color?: string }) {
  const angle = -135 + value * 270;
  return (
    <div className="knob-wrap">
      <div className="knob" style={{ transform: `rotate(${angle}deg)` }}>
        <div className="knob-dot" style={{ background: color }} />
      </div>
      <span className="knob-label">{label}</span>
      <style>{`
        .knob-wrap { display: flex; flex-direction: column; align-items: center; gap: 3px; }
        .knob {
          width: 28px; height: 28px; border-radius: 50%;
          background: #1c1c1c; border: 1.5px solid #2e2e2e;
          position: relative; display: flex; align-items: flex-start; justify-content: center;
          padding-top: 3px;
        }
        .knob-dot { width: 4px; height: 4px; border-radius: 50%; }
        .knob-label { font-family: var(--mono); font-size: 9px; color: var(--text-3); letter-spacing: .05em; }
      `}</style>
    </div>
  );
}

// ── Mixer center ──────────────────────────────────────────────────────────────

function Mixer({
  currentBar, totalBars, playerState, onPlay, onPause, refBpm, audioReady,
}: {
  currentBar: number; totalBars: number;
  playerState: string; onPlay: () => void; onPause: () => void; refBpm: number;
  audioReady: boolean;
}) {
  const playing = playerState === "playing";
  const crossPct = totalBars > 0 ? (currentBar / totalBars) * 100 : 0;

  return (
    <div className="mixer">
      <div className="mixer-label">MIXER</div>

      {/* EQ section — decorative */}
      <div className="mixer-eq">
        <div className="mixer-eq-col">
          <EqKnob label="HI" value={0.72} color="var(--orange)" />
          <EqKnob label="MID" value={0.55} color="var(--orange)" />
          <EqKnob label="LO" value={0.6} color="var(--orange)" />
        </div>
        <div className="mixer-eq-divider" />
        <div className="mixer-eq-col">
          <EqKnob label="HI" value={0.5} color="var(--blue)" />
          <EqKnob label="MID" value={0.6} color="var(--blue)" />
          <EqKnob label="LO" value={0.55} color="var(--blue)" />
        </div>
      </div>

      {/* Crossfader */}
      <div className="mixer-xfader">
        <span className="mixer-xf-label">A</span>
        <div className="mixer-xf-track">
          <div className="mixer-xf-fill" style={{ width: `${crossPct}%` }} />
          <div className="mixer-xf-thumb" style={{ left: `${crossPct}%` }} />
        </div>
        <span className="mixer-xf-label">B</span>
      </div>

      {/* Transport */}
      <div className="mixer-transport">
        <button
          className={`mixer-play${playing ? " mixer-play--active" : ""}`}
          onClick={playing ? onPause : onPlay}
          disabled={!audioReady || playerState === "idle" || playerState === "error"}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <div className="mixer-bpm-display">
          <span className="mixer-bpm-val">{refBpm.toFixed(1)}</span>
          <span className="mixer-bpm-unit">BPM</span>
        </div>
      </div>

      {/* State badge */}
      <div className={`mixer-state mixer-state--${playerState}`}>{playerState}</div>

      <style>{`
        .mixer {
          width: 160px; flex-shrink: 0; display: flex; flex-direction: column;
          align-items: center; gap: 12px; padding: 14px 12px;
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: 0;
        }
        .mixer-label {
          font-size: 10px; font-weight: 600; letter-spacing: .14em;
          color: var(--text-3); text-transform: uppercase;
        }
        .mixer-eq {
          display: flex; gap: 10px; align-items: center; width: 100%; justify-content: center;
        }
        .mixer-eq-col { display: flex; flex-direction: column; gap: 8px; }
        .mixer-eq-divider { width: 1px; height: 100%; background: var(--border); align-self: stretch; }

        .mixer-xfader {
          display: flex; align-items: center; gap: 6px; width: 100%;
        }
        .mixer-xf-label {
          font-family: var(--mono); font-size: 10px; font-weight: 600;
          color: var(--text-2); width: 12px; text-align: center;
        }
        .mixer-xf-track {
          flex: 1; height: 3px; background: var(--border); border-radius: 2px;
          position: relative;
        }
        .mixer-xf-fill {
          height: 100%; background: linear-gradient(90deg, var(--orange), var(--blue));
          border-radius: 2px; transition: width .2s linear;
        }
        .mixer-xf-thumb {
          position: absolute; top: 50%; transform: translate(-50%,-50%);
          width: 10px; height: 10px; border-radius: 50%;
          background: var(--text); border: 2px solid var(--surface3);
          transition: left .2s linear;
        }

        .mixer-transport {
          display: flex; align-items: center; gap: 10px;
        }
        .mixer-play {
          width: 40px; height: 40px; border-radius: 50%;
          background: var(--surface3); border: 2px solid var(--border2);
          font-size: 15px; display: flex; align-items: center; justify-content: center;
          transition: border-color .15s, background .15s;
        }
        .mixer-play--active {
          border-color: var(--orange); background: var(--orange-lo);
          box-shadow: 0 0 12px rgba(255,95,0,.25);
        }
        .mixer-play:not(:disabled):hover { border-color: var(--orange); }
        .mixer-play:not(:disabled):active { transform: scale(.93); }
        .mixer-play:disabled { opacity: .3; cursor: not-allowed; }

        .mixer-bpm-display { display: flex; flex-direction: column; align-items: flex-start; }
        .mixer-bpm-val { font-family: var(--mono); font-size: 18px; font-weight: 600; color: var(--text); line-height: 1; }
        .mixer-bpm-unit { font-size: 9px; letter-spacing: .1em; color: var(--text-2); text-transform: uppercase; }

        .mixer-state {
          font-family: var(--mono); font-size: 10px; letter-spacing: .08em;
          padding: 2px 8px; border-radius: 3px; text-transform: uppercase;
          background: var(--surface3); color: var(--text-2);
        }
        .mixer-state--playing   { color: var(--green); background: rgba(48,209,88,.1); }
        .mixer-state--buffering { color: var(--orange); background: var(--orange-lo); }
        .mixer-state--error     { color: var(--red); background: rgba(255,55,95,.1); }
        .mixer-state--paused    { color: var(--blue); background: var(--blue-lo); }
      `}</style>
    </div>
  );
}

// ── Event timeline strip ───────────────────────────────────────────────────────

function EventStrip({
  script, refBpm, currentBar, showReasoning, onToggleReasoning,
}: {
  script: MixScript; refBpm: number; currentBar: number;
  showReasoning: boolean; onToggleReasoning: () => void;
}) {
  const sorted = [...script.actions].sort((a, b) => actionBar(a) - actionBar(b));
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [currentBar]);

  return (
    <div className="strip-root">
      <div className="strip-header">
        <span className="strip-title">TIMELINE</span>
        <button className="strip-reason-btn" onClick={onToggleReasoning}>
          {showReasoning ? "▲" : "▼"} claude's reasoning
        </button>
      </div>

      {showReasoning && (
        <div className="strip-reasoning">{script.reasoning}</div>
      )}

      <div className="strip-scroll">
        {sorted.map((action, i) => {
          const bar  = actionBar(action);
          const past = bar < currentBar;
          const now  = bar >= currentBar && bar < currentBar + 8;
          return (
            <div
              key={i}
              ref={now ? activeRef : undefined}
              className={`strip-event${past ? " strip-event--past" : ""}${now ? " strip-event--now" : ""}`}
            >
              <div className="strip-event-pip" style={{ background: ACTION_COLOR[action.type] ?? "#555" }} />
              <span className="strip-event-bar">{barToMmss(bar, refBpm)}</span>
              <span className="strip-event-track" style={{ color: action.track === "T1" ? "var(--orange)" : "var(--blue)" }}>
                {action.track}
              </span>
              <span className="strip-event-type">{action.type.replace(/_/g, "​·​")}</span>
              {action.duration_bars != null && (
                <span className="strip-event-detail">{action.duration_bars}b</span>
              )}
              {action.loop_bars != null && (
                <span className="strip-event-detail">{action.loop_bars}×{action.loop_repeats}</span>
              )}
            </div>
          );
        })}
      </div>

      <style>{`
        .strip-root {
          border-top: 1px solid var(--border); flex-shrink: 0;
          display: flex; flex-direction: column; min-height: 0;
        }
        .strip-header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 6px 14px; border-bottom: 1px solid var(--border);
        }
        .strip-title {
          font-size: 10px; font-weight: 600; letter-spacing: .14em;
          color: var(--text-3); text-transform: uppercase;
        }
        .strip-reason-btn {
          font-size: 10px; color: var(--text-2); padding: 2px 8px;
          border: 1px solid var(--border); border-radius: 3px;
          font-family: var(--mono);
        }
        .strip-reason-btn:hover { border-color: var(--border2); color: var(--text); }
        .strip-reasoning {
          padding: 10px 14px; font-size: 12px; color: var(--text-2);
          line-height: 1.6; max-height: 120px; overflow-y: auto;
          border-bottom: 1px solid var(--border); background: var(--surface);
        }
        .strip-scroll {
          display: flex; overflow-x: auto; padding: 6px 8px; gap: 4px;
          flex-shrink: 0; min-height: 52px;
        }
        .strip-event {
          display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
          padding: 6px 10px; background: var(--surface2); border: 1px solid var(--border);
          border-radius: 3px; flex-shrink: 0; min-width: 72px;
          position: relative; cursor: default;
        }
        .strip-event--past { opacity: .3; }
        .strip-event--now  {
          background: var(--surface3); border-color: var(--orange);
          box-shadow: 0 0 8px rgba(255,95,0,.15);
        }
        .strip-event-pip {
          position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 3px 3px 0 0;
        }
        .strip-event-bar   { font-family: var(--mono); font-size: 11px; color: var(--text-2); }
        .strip-event-track { font-family: var(--mono); font-size: 10px; font-weight: 600; }
        .strip-event-type  { font-size: 11px; color: var(--text); white-space: nowrap; }
        .strip-event-detail { font-family: var(--mono); font-size: 10px; color: var(--text-2); }
      `}</style>
    </div>
  );
}

// ── Root player ───────────────────────────────────────────────────────────────

export default function MixPlayer({
  djState,
}: {
  djId: string;
  djState: DjState | null;
}) {
  const sessionId  = djState?.session_id ?? null;
  const script     = djState?.script ?? null;
  const ref_bpm    = djState?.ref_bpm ?? 120;
  const audioReady = !!sessionId;

  // Open WebSocket only once session_id is available (T1 loaded)
  const [status, controls] = usePlayer(sessionId);
  const [showReasoning, setShowReasoning] = useState(false);

  const totalBars = script ? estimateTotalBars(script) : 0;

  // Deck A/B come from djState; fall back to script tracks if available
  const t1 = script?.tracks.find((t) => t.id === djState?.deck_a?.track_id) ?? script?.tracks[0];
  const t2 = script?.tracks.find((t) => t.id === djState?.deck_b?.track_id) ?? script?.tracks[1];

  // Booting overlay — DJ worker is starting T1
  if (!sessionId || !script) {
    return (
      <div className="mp-boot">
        <ClawdDJ state="buffering" size={56} />
        <div className="mp-boot-text">
          <div className="mp-boot-title">
            {djState?.status === "error"
              ? "Error"
              : djState?.deck_b?.status === "analyzing"
              ? `Analyzing ${djState.deck_b.title}…`
              : "Loading first track…"}
          </div>
          <div className="mp-boot-sub">
            {djState?.error ?? "Claude is preparing the mix"}
          </div>
        </div>
        <style>{`
          .mp-boot {
            height: 100%; display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 20px;
            background: var(--bg);
          }
          .mp-boot-text { display: flex; flex-direction: column; gap: 6px; text-align: center; }
          .mp-boot-title { font-size: 18px; font-weight: 700; color: var(--text); }
          .mp-boot-sub   { font-size: 13px; color: var(--text-2); }
        `}</style>
      </div>
    );
  }

  return (
    <div className="mp-root">
      {/* Buffer meter */}
      <div className="mp-topbar">
        <div className="mp-buf-meter" title={`Buffer: ${status.bufferDepthBars} bars`}>
          <span className="mp-buf-label">BUF</span>
          <div className="mp-buf-track">
            <div className="mp-buf-fill" style={{
              width: `${Math.min(100, (status.bufferDepthBars / 32) * 100)}%`
            }} />
          </div>
          <span className="mp-buf-val">{status.bufferDepthBars}b</span>
        </div>

        {djState?.deck_b && (
          <div className="mp-deck-b-status">
            <span className="mp-deck-b-label">{djState.deck_b.status.toUpperCase()}</span>
            <span className="mp-deck-b-title">{djState.deck_b.title}</span>
          </div>
        )}
      </div>

      {/* Waveform */}
      <Waveform
        script={script}
        totalBars={totalBars}
        currentBar={status.currentBar}
        bufferBars={status.bufferDepthBars}
        onSeek={controls.seek}
      />

      {/* Decks + mixer */}
      <div className="mp-decks">
        <Deck track={t1} side="A" currentBar={status.currentBar} totalBars={totalBars} script={script} />
        <Mixer
          currentBar={status.currentBar}
          totalBars={totalBars}
          playerState={status.state}
          onPlay={controls.play}
          onPause={controls.pause}
          refBpm={ref_bpm}
          audioReady={audioReady}
        />
        <Deck track={t2} side="B" currentBar={status.currentBar} totalBars={totalBars} script={script} />
      </div>

      {/* Event strip */}
      <EventStrip
        script={script}
        refBpm={ref_bpm}
        currentBar={status.currentBar}
        showReasoning={showReasoning}
        onToggleReasoning={() => setShowReasoning((v) => !v)}
      />

      {status.error && (
        <div className="mp-error">{status.error}</div>
      )}

      <style>{`
        .mp-root {
          display: flex; flex-direction: column; height: 100%; overflow: hidden;
          background: var(--bg);
        }
        .mp-topbar {
          display: flex; align-items: center; gap: 14px; padding: 5px 14px;
          background: var(--surface); border-bottom: 1px solid var(--border);
          flex-shrink: 0;
        }
        .mp-buf-meter {
          display: flex; align-items: center; gap: 6px;
          font-family: var(--mono); font-size: 10px; color: var(--text-2);
        }
        .mp-buf-label { letter-spacing: .08em; }
        .mp-buf-track {
          width: 60px; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden;
        }
        .mp-buf-fill {
          height: 100%; background: var(--green); border-radius: 2px; transition: width .3s;
        }
        .mp-buf-val { color: var(--text-3); }

        .mp-deck-b-status {
          display: flex; align-items: center; gap: 6px;
          font-family: var(--mono);
        }
        .mp-deck-b-label {
          font-size: 9px; font-weight: 700; letter-spacing: .12em;
          color: var(--blue); background: var(--blue-lo);
          padding: 1px 5px; border-radius: 3px;
        }
        .mp-deck-b-title {
          font-size: 11px; color: var(--text-2); max-width: 200px;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }

        .mp-decks {
          display: flex; flex: 1; min-height: 0; overflow: hidden;
        }

        .mp-error {
          position: fixed; bottom: 20px; right: 20px;
          background: rgba(255,55,95,.15); border: 1px solid var(--red);
          color: var(--red); padding: 8px 14px; border-radius: var(--radius);
          font-size: 12px; font-family: var(--mono);
        }
      `}</style>
    </div>
  );
}

