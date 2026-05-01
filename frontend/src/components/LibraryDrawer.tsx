import { useState } from 'react';
import QueueStrip from './QueueStrip';
import TrackList from './TrackList';
import type { LibraryScanJob, LibraryTrack } from '../types';

interface Props {
  tracks:       LibraryTrack[];
  scanJob:      LibraryScanJob | null;
  playingHash:  string | null;
  queuedHashes: string[];
  open:         boolean;
  onToggle:     () => void;
  onScan:       () => void;
  onEnqueue:    (hash: string) => void;
  trackByHash:  (hash: string) => LibraryTrack | undefined;
}

export default function LibraryDrawer({
  tracks, scanJob, playingHash, queuedHashes,
  open, onToggle, onScan, onEnqueue, trackByHash,
}: Props) {
  const [filter, setFilter] = useState('');
  const scanning = scanJob?.status === 'running';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface)',
      borderTop: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      {/* Tab / header */}
      <div
        onClick={onToggle}
        style={{
          height: 32,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 12px',
          cursor: 'pointer',
          borderBottom: open ? '1px solid var(--border)' : 'none',
          flexShrink: 0,
          userSelect: 'none',
        }}
      >
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '.14em',
          color: 'var(--text-3)',
          textTransform: 'uppercase',
        }}>
          {open ? '▾' : '▸'} LIBRARY
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-3)',
          background: 'var(--surface2)',
          padding: '1px 6px',
          borderRadius: 3,
        }}>
          {tracks.length}
        </span>

        <div style={{ flex: 1 }} />

        {/* Scan progress inline */}
        {scanning && scanJob && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)' }}>
            {scanJob.progress} / {scanJob.total}
          </span>
        )}

        <button
          onClick={(e) => { e.stopPropagation(); onScan(); }}
          disabled={scanning}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            padding: '2px 10px',
            borderRadius: 3,
            background: 'var(--surface2)',
            color: 'var(--text-2)',
            border: '1px solid var(--border2)',
            opacity: scanning ? 0.4 : 1,
            cursor: scanning ? 'not-allowed' : 'pointer',
          }}
        >
          {scanning ? 'Scanning…' : 'Scan Folder'}
        </button>
      </div>

      {/* Drawer content */}
      {open && (
        <>
          {/* Scan result bar */}
          {scanJob && scanJob.status !== 'running' && (
            <div style={{
              padding: '4px 12px',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: scanJob.status === 'error' ? 'var(--red)' : 'var(--text-3)',
              borderBottom: '1px solid var(--border)',
              flexShrink: 0,
            }}>
              {scanJob.status === 'error'
                ? scanJob.error
                : `Done · ${scanJob.new} new, ${scanJob.known} cached`}
            </div>
          )}

          {/* Search */}
          <div style={{ padding: '6px 10px', flexShrink: 0 }}>
            <input
              style={{ width: '100%', fontSize: 12 }}
              placeholder="Filter by title, artist, key…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
            />
          </div>

          {/* Column headers */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '3px 10px',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            <div style={{ width: 10 }} />
            <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', letterSpacing: '.1em' }}>TRACK</span>
            <span style={{ width: 80, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)' }}>WAVE</span>
            <span style={{ width: 54, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', textAlign: 'right' }}>BPM / KEY</span>
            <div style={{ width: 30 }} />
          </div>

          {/* Queue strip */}
          <QueueStrip queuedHashes={queuedHashes} trackByHash={trackByHash} />

          {/* Track list */}
          <TrackList
            tracks={tracks}
            playingHash={playingHash}
            queuedHashes={queuedHashes}
            filter={filter}
            onEnqueue={onEnqueue}
          />
        </>
      )}
    </div>
  );
}
