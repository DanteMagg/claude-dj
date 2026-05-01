import type { PlayerState } from '../types';

interface Props {
  playerState:     PlayerState;
  currentBar:      number;
  startBar:        number;
  totalBars:       number;
  bufferDepthBars: number;
  trackNumber:     number;
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
  startBar,
  totalBars,
  bufferDepthBars,
  trackNumber,
  onSeek,
  onStop,
}: Props) {
  const relBar    = Math.max(0, currentBar - startBar);
  const pct       = totalBars > 0 ? Math.min(1, relBar / totalBars) : 0;
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

      {/* Track # + bar counter */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--text-3)',
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}>
        {trackNumber > 0 && (
          <span style={{ color: 'var(--orange)', marginRight: 6 }}>T{trackNumber}</span>
        )}
        {String(relBar).padStart(3, ' ')} / {totalBars}
      </span>

      {/* Progress bar — read-only, no seeking (would break the DJ pipeline) */}
      <div
        style={{
          flex: 1,
          height: 4,
          background: 'var(--border)',
          borderRadius: 2,
          position: 'relative',
          cursor: 'default',
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
