import { useCallback, useEffect, useState } from 'react';
import TopBar from './components/TopBar';
import DeckRow from './components/DeckRow';
import WaveformStrip from './components/WaveformStrip';
import TransportBar from './components/TransportBar';
import LibraryDrawer from './components/LibraryDrawer';
import { useDjSession } from './hooks/useDjSession';
import { useLibrary } from './hooks/useLibrary';
import { usePlayer } from './hooks/usePlayer';
import { useTransitionLog } from './hooks/useTransitionLog';
import type { DjStartOpts } from './types';

const DRAWER_OPEN_KEY = 'claude-dj:drawer-open';

export default function App() {
  const [model,      setModel]      = useState('claude-haiku-4-5-20251001');
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
  const transitionLog = useTransitionLog(djId);

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
      pool:  tracks.map(t => t.hash),
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
  const deckB  = djState?.deck_b ?? null;
  const trackB = deckB
    ? (deckB.hash ? trackByHash(deckB.hash) : trackByTitle(deckB.title))
    : undefined;

  // Only expose reasoning text when deck B has finished planning (status = 'ready').
  // While still working (analyzing/planning/loading), pass '' so the status badge
  // shows and the typewriter doesn't fire on stale text.
  const latestReasoning = (() => {
    if (djState?.deck_b?.status !== 'ready') return '';
    const full = djState?.script?.reasoning ?? '';
    const parts = full.split(/\n---\n/);
    return parts[parts.length - 1].trim();
  })();

  // Derive actual transition bar from planned script:
  // find the first upcoming fade_in for a track that isn't deck A,
  // with start_bar AFTER the current deck A's start (to skip past transitions in the merged script).
  const transitionBar = (() => {
    const deckAId  = djState?.deck_a?.track_id;
    const deckAStart = djState?.deck_a?.start_bar ?? 0;
    const act = djState?.script?.actions?.find(
      a => a.type === 'fade_in'
        && a.track !== deckAId
        && (a.start_bar ?? 0) > deckAStart,
    );
    return act ? (act.start_bar ?? null) : null;
  })();

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
        canStart={tracks.length > 0}
        onStart={handleStart}
        onStop={handleStop}
        onModelChange={setModel}
        onClaudePickChange={setClaudePick}
      />

      <DeckRow
        deckA={djState?.deck_a ?? null}
        deckB={djState?.deck_b ?? null}
        reasoning={latestReasoning}
        trackByHash={trackByHash}
        trackByTitle={trackByTitle}
      />

      <WaveformStrip
        trackA={trackA}
        trackB={trackB}
        currentBar={currentBar}
        startBar={djState?.deck_a?.start_bar ?? 0}
        transitionBar={transitionBar}
        onSeek={handleSeek}
      />

      <TransportBar
        playerState={playerState}
        currentBar={currentBar}
        startBar={djState?.deck_a?.start_bar ?? 0}
        totalBars={totalBars}
        bufferDepthBars={bufferDepthBars}
        trackNumber={djState?.deck_a ? parseInt(djState.deck_a.track_id.replace('T', '')) : 0}
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
        transitionLog={transitionLog}
      />
    </div>
  );
}
