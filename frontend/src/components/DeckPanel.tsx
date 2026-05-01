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
