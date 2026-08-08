import type { MixAction, MixScript } from "../types";
import { barToMmss } from "../utils";

interface Props {
  script: MixScript;
  refBpm: number;
  currentBar: number;
}

function actionBar(a: MixAction): number {
  return a.at_bar ?? a.start_bar ?? a.bar ?? 0;
}

const TYPE_LABELS: Record<string, string> = {
  play:      "play",
  fade_in:   "fade in",
  fade_out:  "fade out",
  bass_swap: "bass swap",
  loop:      "loop",
  eq:        "eq",
};

export default function TransitionLog({ script, refBpm, currentBar }: Props) {
  const sorted = [...script.actions].sort((a, b) => actionBar(a) - actionBar(b));

  return (
    <div className="tlog">
      <div className="tlog-header">Timeline</div>
      <div className="tlog-scroll">
        {sorted.map((action, i) => {
          const bar  = actionBar(action);
          const past = bar < currentBar;
          const now  = bar >= currentBar && bar < currentBar + 8;
          return (
            <div key={i} className={`tlog-row ${past ? "past" : ""} ${now ? "now" : ""}`}>
              <span className="tlog-bar">{bar}</span>
              <span className="tlog-time">{barToMmss(bar, refBpm)}</span>
              <span className="tlog-track">{action.track}</span>
              <span className="tlog-type">{TYPE_LABELS[action.type] ?? action.type}</span>
              {action.duration_bars != null && (
                <span className="tlog-dur">{action.duration_bars}b</span>
              )}
              {action.loop_bars != null && (
                <span className="tlog-dur">{action.loop_bars}b×{action.loop_repeats}</span>
              )}
            </div>
          );
        })}
      </div>

      <style>{`
        .tlog {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          overflow: hidden;
          flex: 1;
          display: flex;
          flex-direction: column;
          min-height: 0;
        }
        .tlog-header {
          padding: 8px 12px;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: .08em;
          text-transform: uppercase;
          color: var(--text-2);
          border-bottom: 1px solid var(--border);
        }
        .tlog-scroll {
          overflow-y: auto;
          flex: 1;
        }
        .tlog-row {
          display: grid;
          grid-template-columns: 40px 48px 36px 1fr auto;
          gap: 8px;
          padding: 5px 12px;
          font-size: 12px;
          font-family: var(--mono);
          border-bottom: 1px solid rgba(42,42,42,.5);
          transition: background .1s;
        }
        .tlog-row.past { opacity: .35; }
        .tlog-row.now {
          background: rgba(255,95,0,.1);
          border-left: 2px solid var(--accent);
        }
        .tlog-bar  { color: var(--text-2); }
        .tlog-time { color: var(--text-3); }
        .tlog-track { color: var(--accent); font-weight: 600; }
        .tlog-type { color: var(--text); }
        .tlog-dur  { color: var(--text-3); text-align: right; }
      `}</style>
    </div>
  );
}
