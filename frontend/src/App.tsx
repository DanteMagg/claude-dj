import { useCallback, useEffect, useState } from 'react';
import TopBar from './components/TopBar';
import DeckRow from './components/DeckRow';
import WaveformStrip from './components/WaveformStrip';
import TransportBar from './components/TransportBar';
import LibraryDrawer from './components/LibraryDrawer';
import { useDjSession } from './hooks/useDjSession';
import { useLibrary } from './hooks/useLibrary';
import { usePlayer } from './hooks/usePlayer';
import type { DjStartOpts } from './types';

const DRAWER_OPEN_KEY = 'claude-dj:drawer-open';

export default function App() {
  const [model,      setModel]      = useState('claude-sonnet-4-6');
  const [claudePick, setClaudePick] = useState(true);
  const [localQueue, setLocalQueue] = useState<string[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(
    () => localStorage.getItem(DRAWER_OPEN_KEY) !== 'false',
  );

  const { tracks, scanJob, scanFolder, trackByHash, trackByTitle } = useLibrary();
  const { djId, djState, error: djError, startDj, stopDj, enqueue } = useDjSession();

  const sessionId  = djState?.session_id ?? null;
  const totalBars  = djState?.deck_a
    ? (trackByHash(djState.deck_a.hash)?.energy_curve.length ?? 128)
    : 128;

  const { playerState, currentBar, bufferDepthBars, seek, stop: stopPlayer } = usePlayer(sessionId);

  // Open drawer automatically if library is empty
  useEffect(() => {
    if (tracks.length === 0) setDrawerOpen(true);
  }, [tracks.length]);

  const toggleDrawer = useCallback(() => {
    setDrawerOpen(v => {
      localStorage.setItem(DRAWER_OPEN_KEY, String(!v));
      return !v;
    });
  }, []);

  const handleScan = useCallback(async () => {
    const folder = await window.electron?.selectFolder() ?? prompt('Folder path to scan:');
    if (folder) scanFolder(folder);
  }, [scanFolder]);

  const handleStart = useCallback((opts: Omit<DjStartOpts, 'pool' | 'queue'>) => {
    startDj({
      ...opts,
      pool:  localQueue.length > 0 ? [] : tracks.map(t => t.hash),
      queue: localQueue,
    });
    setLocalQueue([]);
  }, [startDj, localQueue, tracks]);

  const handleStop = useCallback(() => {
    stopPlayer();
    stopDj();
  }, [stopPlayer, stopDj]);

  const handleEnqueue = useCallback(async (hash: string) => {
    if (djId) {
      await enqueue(hash);
    } else {
      setLocalQueue(q => q.includes(hash) ? q : [...q, hash]);
    }
  }, [djId, enqueue]);

  const handleSeek = useCallback((bar: number) => {
    seek(bar);
  }, [seek]);

  const playingHash  = djState?.deck_a?.hash ?? null;
  const queuedHashes = djState?.queue ?? localQueue;

  const trackA = djState?.deck_a ? trackByHash(djState.deck_a.hash) : undefined;
  const trackB = djState?.deck_b ? trackByTitle(djState.deck_b.title) : undefined;

  return (
    <div style={{
      display: 'grid',
      height: '100vh',
      gridTemplateRows: drawerOpen
        ? '32px 1fr 64px 44px 45vh'
        : '32px 1fr 64px 44px 32px',
      overflow: 'hidden',
      transition: 'grid-template-rows .25s ease',
    }}>
      <TopBar
        isActive={!!djId}
        refBpm={djState?.ref_bpm ?? null}
        model={model}
        claudePick={claudePick}
        error={djError}
        onStart={handleStart}
        onStop={handleStop}
        onModelChange={setModel}
        onClaudePickChange={setClaudePick}
      />

      <DeckRow
        deckA={djState?.deck_a ?? null}
        deckB={djState?.deck_b ?? null}
        sessionId={sessionId}
        trackByHash={trackByHash}
        trackByTitle={trackByTitle}
      />

      <WaveformStrip
        trackA={trackA}
        trackB={trackB}
        currentBar={currentBar}
        onSeek={handleSeek}
      />

      <TransportBar
        playerState={playerState}
        currentBar={currentBar}
        totalBars={totalBars}
        bufferDepthBars={bufferDepthBars}
        onSeek={handleSeek}
        onStop={handleStop}
      />

      <LibraryDrawer
        tracks={tracks}
        scanJob={scanJob}
        playingHash={playingHash}
        queuedHashes={queuedHashes}
        open={drawerOpen}
        onToggle={toggleDrawer}
        onScan={handleScan}
        onEnqueue={handleEnqueue}
        trackByHash={trackByHash}
      />
    </div>
  );
}
