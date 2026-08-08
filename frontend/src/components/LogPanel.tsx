import { useState } from 'react';
import type { LoggedAction, TransitionLogEntry } from '../hooks/useTransitionLog';

// ── Action badge helpers ──────────────────────────────────────────────────────

const ACTION_COLOR: Record<string, string> = {
  play:       'var(--green)',
  fade_in:    'var(--blue)',
  fade_out:   'var(--orange)',
  bass_swap:  'var(--purple)',
  eq:         '#ffd60a',
  loop:       '#30d158',
};

function actionLabel(a: LoggedAction): string {
  switch (a.type) {
    case 'play':
      return `play ${a.track} @${a.at_bar ?? '?'}`;
    case 'fade_in': {
      const dur = a.duration_bars != null ? ` ${a.duration_bars}b` : '';
      const stems = a.stems
        ? ' stems:' + Object.entries(a.stems).map(([k, v]) => `${k[0]}=${v.toFixed(1)}`).join(',')
        : '';
      return `fade_in ${a.track} @${a.start_bar ?? '?'}${dur}${stems}`;
    }
    case 'fade_out': {
      const dur = a.duration_bars != null ? ` ${a.duration_bars}b` : '';
      return `fade_out ${a.track} @${a.start_bar ?? '?'}${dur}`;
    }
    case 'bass_swap': {
      const inc = a.incoming_track ? ` → restore ${a.incoming_track}` : '';
      return `bass_swap ${a.track} @${a.at_bar ?? '?'}${inc}`;
    }
    case 'eq': {
      const lo  = a.low  != null ? `lo=${a.low.toFixed(2)}` : null;
      const mid = a.mid  != null ? `mid=${a.mid.toFixed(2)}` : null;
      const hi  = a.high != null ? `hi=${a.high.toFixed(2)}` : null;
      const bands = [lo, mid, hi].filter(Boolean).join(' ');
      return `eq ${a.track} @${a.bar ?? '?'} ${bands}`;
    }
    case 'loop':
      return `loop ${a.track} @${a.start_bar ?? '?'} ${a.loop_bars}b×${a.loop_repeats}`;
    default:
      return `${a.type} ${a.track}`;
  }
}

// Highlight potentially problematic patterns
function actionWarning(a: LoggedAction): string | null {
  if (a.type === 'eq' && a.low != null && a.low > 0.8)
    return 'low≈1 — bass not cut, risk of mud';
  if (a.type === 'fade_in' && !a.stems)
    return 'no stem blend — full track fades in';
  return null;
}

// ── Entry component ───────────────────────────────────────────────────────────

function LogEntry({ entry }: { entry: TransitionLogEntry }) {
  const [open, setOpen] = useState(false);

  const hasBassSwap = entry.actions.some(a => a.type === 'bass_swap');
  const eqActions   = entry.actions.filter(a => a.type === 'eq');
  const lowValues   = eqActions.flatMap(a => a.low != null ? [a.low] : []);
  const bassWarning = !hasBassSwap && entry.actions.some(a =>
    a.type === 'fade_in' || a.type === 'fade_out'
  );

  const time = new Date(entry.ts).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  return (
    <div style={{
      borderBottom: '1px solid var(--border)',
      padding: '10px 14px',
    }}>
      {/* Header row */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 8,
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--text-3)',
          minWidth: 68,
        }}>{time}</span>

        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--orange)',
          fontWeight: 700,
        }}>{entry.from_id}</span>

        <span style={{ color: 'var(--text-3)', fontSize: 10 }}>→</span>

        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--blue)',
          fontWeight: 700,
        }}>{entry.to_id}</span>

        <span style={{
          fontSize: 11,
          color: 'var(--text-2)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flex: 1,
        }}>
          {entry.from_title} → {entry.to_title}
        </span>

        {/* Flags */}
        {bassWarning && (
          <span title="No bass_swap — both basslines may overlap" style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--yellow)',
            background: 'rgba(255,214,10,0.12)',
            padding: '1px 5px',
            borderRadius: 2,
          }}>NO SWAP</span>
        )}
        {lowValues.some(v => v > 0.8) && (
          <span title="EQ low≈1.0 — bass not cut" style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--orange)',
            background: 'rgba(255,95,0,0.12)',
            padding: '1px 5px',
            borderRadius: 2,
          }}>BASS ON</span>
        )}

        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--text-3)',
          marginLeft: 4,
        }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {/* Reasoning */}
          {entry.reasoning && (
            <p style={{
              fontSize: 11,
              color: 'var(--text-2)',
              lineHeight: 1.65,
              margin: '0 0 10px',
              fontFamily: 'var(--font-ui)',
              borderLeft: '2px solid var(--purple)',
              paddingLeft: 10,
            }}>
              {entry.reasoning}
            </p>
          )}

          {/* Action list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {entry.actions.map((a, i) => {
              const warn = actionWarning(a);
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    fontWeight: 700,
                    color: ACTION_COLOR[a.type] ?? 'var(--text-2)',
                    minWidth: 60,
                  }}>{a.type.toUpperCase()}</span>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    color: 'var(--text)',
                  }}>{actionLabel(a)}</span>
                  {warn && (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 9,
                      color: 'var(--yellow)',
                      marginLeft: 6,
                    }}>⚠ {warn}</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Summary badges */}
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            <span style={badgeStyle('var(--green)')}>
              T2 @bar {entry.offset_bar}
            </span>
            {hasBassSwap && (
              <span style={badgeStyle('var(--purple)')}>bass_swap ✓</span>
            )}
            {lowValues.length > 0 && (
              <span style={badgeStyle(lowValues.some(v => v > 0.8) ? 'var(--orange)' : 'var(--blue)')}>
                low EQ: {lowValues.map(v => v.toFixed(2)).join(', ')}
              </span>
            )}
            {!hasBassSwap && entry.actions.some(a => a.type === 'fade_in') && (
              <span style={badgeStyle('var(--yellow)')}>⚠ no bass_swap</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function badgeStyle(color: string): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 9,
    fontWeight: 700,
    color,
    background: color.replace(')', ',0.12)').replace('var(', 'rgba(').replace(')', ')'),
    padding: '2px 6px',
    borderRadius: 3,
    letterSpacing: '.05em',
  };
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  log: TransitionLogEntry[];
}

export default function LogPanel({ log }: Props) {
  if (log.length === 0) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: 'var(--text-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
      }}>
        No transitions logged yet
      </div>
    );
  }

  return (
    <div style={{ overflowY: 'auto', flex: 1 }}>
      {log.map((entry, i) => (
        <LogEntry key={i} entry={entry} />
      ))}
    </div>
  );
}
