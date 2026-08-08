import TrackRow from './TrackRow';
import type { LibraryTrack } from '../types';

interface Props {
  tracks:       LibraryTrack[];
  playingHash:  string | null;
  queuedHashes: string[];
  filter:       string;
  onEnqueue:    (hash: string) => void;
}

export default function TrackList({ tracks, playingHash, queuedHashes, filter, onEnqueue }: Props) {
  const filtered = filter
    ? tracks.filter(t =>
        t.title.toLowerCase().includes(filter.toLowerCase()) ||
        t.artist.toLowerCase().includes(filter.toLowerCase()) ||
        t.key_camelot.toLowerCase().includes(filter.toLowerCase()),
      )
    : tracks;

  if (filtered.length === 0) {
    return (
      <div style={{
        padding: '32px 20px', textAlign: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color: 'var(--text-3)', letterSpacing: '.04em',
      }}>
        {tracks.length === 0 ? 'Scan a folder to add tracks' : 'No tracks match the filter'}
      </div>
    );
  }

  return (
    <div style={{ overflowY: 'auto', flex: 1 }}>
      {filtered.map(t => (
        <TrackRow
          key={t.hash}
          track={t}
          isPlaying={t.hash === playingHash}
          isQueued={queuedHashes.includes(t.hash)}
          onEnqueue={onEnqueue}
        />
      ))}
    </div>
  );
}
