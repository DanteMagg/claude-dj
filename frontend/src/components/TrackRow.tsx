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
