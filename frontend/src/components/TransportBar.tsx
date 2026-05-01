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
