import type { LibraryTrack } from '../types';

interface Props {
  queuedHashes: string[];
  trackByHash:  (hash: string) => LibraryTrack | undefined;
}

export default function QueueStrip({ queuedHashes, trackByHash }: Props) {
  if (queuedHashes.length === 0) return null;

  return (
    <div style={{
      display: 'flex',
      gap: 6,
      padding: '6px 10px',
      overflowX: 'auto',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {queuedHashes.map((hash, i) => {
        const t = trackByHash(hash);
        return (
          <div
            key={hash}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 8px', borderRadius: 3,
              background: 'var(--blue-lo)',
              border: '1px solid rgba(0,180,255,0.2)',
              flexShrink: 0,
            }}
          >
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--blue)', marginRight: 2,
            }}>
              {i + 1}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
              {t?.title ?? hash.slice(0, 8)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
