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
