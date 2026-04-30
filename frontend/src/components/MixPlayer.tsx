import { useEffect, useRef, useState } from "react";
import TransitionLog from "./TransitionLog";
import { usePlayer } from "../hooks/usePlayer";
import type { MixScript, Session } from "../types";

function barToMmss(bar: number, bpm: number): string {
  const ms = Math.round((bar * 4 * 60_000) / bpm);
  const s  = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

interface Props {
  session: Session;
}

const BUFFER_DISPLAY_MAX_BARS = 32;

function estimateTotalBars(script: MixScript): number {
  let max = 0;
  for (const a of script.actions) {
    const b = (a.at_bar ?? a.start_bar ?? a.bar ?? 0) + (a.duration_bars ?? 0);
    if (b > max) max = b;
  }
  return max + 32;
}

function activeTrackLabel(script: MixScript, currentBar: number): string {
  const plays = script.actions
    .filter((a) => a.type === "play" && (a.at_bar ?? 0) <= currentBar)
    .sort((a, b) => (b.at_bar ?? 0) - (a.at_bar ?? 0));
  if (!plays[0]) return "";
  const tid = plays[0].track;
  const ref = script.tracks.find((t) => t.id === tid);
  return ref ? `${tid} · ${ref.bpm} BPM` : tid;
}

export default function MixPlayer({ session }: Props) {
  const { session_id, script, ref_bpm } = session;
  const [playerStatus, controls] = usePlayer(session_id);
  const totalBars = estimateTotalBars(script);
  const progressPct = totalBars > 0 ? (playerStatus.currentBar / totalBars) * 100 : 0;
  const seekBarRef  = useRef<HTMLInputElement>(null);
  const [showReasoning, setShowReasoning] = useState(false);

  useEffect(() => {
    if (seekBarRef.current) {
      seekBarRef.current.value = String(playerStatus.currentBar);
    }
  }, [playerStatus.currentBar]);

  const bufferPct = Math.min(100, (playerStatus.bufferDepthBars / BUFFER_DISPLAY_MAX_BARS) * 100);

  return (
    <div className="player-root">
      {/* Header */}
      <div className="player-header">
        <span className="mix-title">{script.mix_title}</span>
        <span className="ref-bpm">{ref_bpm.toFixed(1)} BPM</span>
        <button
          className="btn-ghost reason-toggle"
          onClick={() => setShowReasoning((v) => !v)}
          title="Claude's reasoning"
        >
          {showReasoning ? "▲" : "▼"} reasoning
        </button>
      </div>

      {showReasoning && (
        <div className="reasoning-box">
          <p>{script.reasoning}</p>
        </div>
      )}

      {/* Now playing */}
      <div className="now-playing">
        <span className="np-label">Now playing</span>
        <span className="np-track">{activeTrackLabel(script, playerStatus.currentBar)}</span>
      </div>

      {/* Progress bar */}
      <div className="progress-wrap">
        <span className="time-label">{barToMmss(playerStatus.currentBar, ref_bpm)}</span>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <span className="time-label">{barToMmss(totalBars, ref_bpm)}</span>
      </div>

      {/* Seek slider */}
      <input
        ref={seekBarRef}
        className="seek-slider"
        type="range"
        min={0}
        max={totalBars}
        defaultValue={0}
        step={8}
        onMouseUp={(e) => controls.seek(Number((e.target as HTMLInputElement).value))}
        onTouchEnd={(e)  => controls.seek(Number((e.target as HTMLInputElement).value))}
      />

      {/* Transport */}
      <div className="transport">
        <button
          className={`btn-transport ${playerStatus.state === "playing" ? "active" : ""}`}
          onClick={playerStatus.state === "playing" ? controls.pause : controls.play}
          disabled={playerStatus.state === "buffering" || playerStatus.state === "idle" || playerStatus.state === "error"}
        >
          {playerStatus.state === "playing" ? "⏸" : "▶"}
        </button>

        <div className="status-block">
          <span className={`state-badge state-${playerStatus.state}`}>
            {playerStatus.state}
          </span>
          {playerStatus.error && (
            <span className="err-msg">{playerStatus.error}</span>
          )}
        </div>

        <div className="buffer-meter" title={`Buffer: ${playerStatus.bufferDepthBars} bars`}>
          <span className="buffer-label">buf</span>
          <div className="buffer-track">
            <div className="buffer-fill" style={{ width: `${bufferPct}%` }} />
          </div>
          <span className="buffer-val">{playerStatus.bufferDepthBars}b</span>
        </div>
      </div>

      {/* Transition log */}
      <div className="log-wrap">
        <TransitionLog script={script} refBpm={ref_bpm} currentBar={playerStatus.currentBar} />
      </div>

      <style>{`
        .player-root {
          display: flex;
          flex-direction: column;
          gap: 14px;
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 20px;
          flex: 1;
          min-height: 0;
        }
        .player-header {
          display: flex;
          align-items: baseline;
          gap: 12px;
        }
        .mix-title {
          font-size: 16px;
          font-weight: 700;
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ref-bpm { font-family: var(--mono); color: var(--accent); font-size: 13px; }
        .btn-ghost {
          font-size: 11px;
          color: var(--text-2);
          padding: 3px 8px;
          border: 1px solid var(--border);
          border-radius: 4px;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .btn-ghost:hover { border-color: var(--accent); color: var(--text); }
        .reasoning-box {
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 12px 14px;
          font-size: 12px;
          color: var(--text-2);
          line-height: 1.6;
          max-height: 160px;
          overflow-y: auto;
        }
        .now-playing {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
        }
        .np-label { color: var(--text-3); text-transform: uppercase; letter-spacing: .07em; font-size: 11px; }
        .np-track  { font-family: var(--mono); color: var(--text); }
        .progress-wrap {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          font-family: var(--mono);
          color: var(--text-2);
        }
        .progress-track {
          flex: 1;
          height: 3px;
          background: var(--border);
          border-radius: 2px;
          overflow: hidden;
        }
        .progress-fill { height: 100%; background: var(--accent); transition: width .2s linear; }
        .time-label { min-width: 36px; }
        .seek-slider {
          width: 100%;
          accent-color: var(--accent);
          height: 4px;
          cursor: pointer;
          background: transparent;
        }
        .transport {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .btn-transport {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: var(--surface2);
          border: 2px solid var(--border);
          font-size: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: border-color .15s, background .15s;
          flex-shrink: 0;
        }
        .btn-transport.active { border-color: var(--accent); background: rgba(255,95,0,.12); }
        .btn-transport:disabled { opacity: .35; cursor: not-allowed; }
        .btn-transport:not(:disabled):hover { border-color: var(--accent); }
        .btn-transport:not(:disabled):active { transform: scale(0.94); }
        .status-block { display: flex; flex-direction: column; gap: 2px; flex: 1; }
        .state-badge {
          font-size: 11px;
          font-family: var(--mono);
          padding: 2px 7px;
          border-radius: 4px;
          width: fit-content;
          background: var(--surface2);
          color: var(--text-2);
        }
        .state-badge.state-playing   { color: var(--green); background: rgba(0,217,126,.1); }
        .state-badge.state-buffering { color: var(--accent); background: rgba(255,95,0,.1); }
        .state-badge.state-error     { color: #ff4d4d; background: rgba(255,77,77,.1); }
        .err-msg { font-size: 11px; color: #ff4d4d; }
        .buffer-meter {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: var(--text-3);
          font-family: var(--mono);
        }
        .buffer-track {
          width: 60px;
          height: 3px;
          background: var(--border);
          border-radius: 2px;
          overflow: hidden;
        }
        .buffer-fill {
          height: 100%;
          background: var(--green);
          border-radius: 2px;
          transition: width .3s;
        }
        .log-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; }
      `}</style>
    </div>
  );
}
