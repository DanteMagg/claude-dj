import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
import ClawdDJ from "./components/ClawdDJ";
import LibraryPanel from "./components/LibraryPanel";
import MixPlayer from "./components/MixPlayer";
import type { DjState, LibraryTrack } from "./types";

const MODELS = [
  { id: "claude-sonnet-4-6",            label: "Sonnet 4.6"  },
  { id: "claude-opus-4-5",              label: "Opus 4.5"    },
  { id: "claude-haiku-4-5-20251001",    label: "Haiku 4.5"   },
];

export default function App() {
  const [djId,         setDjId]         = useState<string | null>(null);
  const [djState,      setDjState]      = useState<DjState | null>(null);
  const [library,      setLibrary]      = useState<LibraryTrack[]>([]);
  const [localQueue,   setLocalQueue]   = useState<string[]>([]);
  const [model,        setModel]        = useState(MODELS[0]!.id);
  const [claudePick,   setClaudePick]   = useState(true);
  const [starting,     setStarting]     = useState(false);
  const [startError,   setStartError]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll DJ session state
  useEffect(() => {
    if (!djId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res   = await apiFetch(`/api/dj/${djId}`);
        const state = (await res.json()) as DjState;
        setDjState(state);
        if (state.status === "error") clearInterval(pollRef.current!);
      } catch { /* ignore transient */ }
    }, 1500);
    return () => clearInterval(pollRef.current!);
  }, [djId]);

  const handleStart = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const res  = await apiFetch("/api/dj/start", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pool:            localQueue.length > 0 ? [] : library.map((t) => t.hash),
          queue:           localQueue,
          let_claude_pick: claudePick,
          model,
        }),
      });
      const data = (await res.json()) as { dj_id?: string; error?: string };
      if (data.error) setStartError(data.error);
      else if (data.dj_id) {
        setDjId(data.dj_id);
        setLocalQueue([]);
      }
    } catch (e) {
      setStartError(String(e));
    } finally {
      setStarting(false);
    }
  };

  const handleEnqueue = useCallback((hash: string) => {
    setLocalQueue((q) => (q.includes(hash) ? q : [...q, hash]));
  }, []);

  const playingHash  = djState?.deck_a?.hash ?? null;
  const queuedHashes = djState?.queue ?? localQueue;

  return (
    <div className="app-root">
      {/* Top bar */}
      <div className="app-topbar">
        <ClawdDJ state={djState?.status === "playing" ? "playing" : "idle"} size={28} />
        <span className="app-brand">CLAUDE DJ</span>

        {djState?.ref_bpm && (
          <span className="app-bpm">
            {djState.ref_bpm.toFixed(1)} <span className="app-bpm-unit">BPM</span>
          </span>
        )}

        {djState?.deck_a && (
          <div className="app-now-playing">
            <span className="app-np-label">NOW PLAYING</span>
            <span className="app-np-title">{djState.deck_a.title}</span>
          </div>
        )}

        {djState?.deck_b && (
          <div className="app-deck-b">
            <span className="app-np-label">{djState.deck_b.status.toUpperCase()}</span>
            <span className="app-np-title app-np-title--b">{djState.deck_b.title}</span>
          </div>
        )}

        <div className="app-topbar-spacer" />

        {!djId && (
          <>
            <div className="app-model-row">
              <select
                className="app-select"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {MODELS.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <label className="app-toggle">
                <input
                  type="checkbox"
                  checked={claudePick}
                  onChange={(e) => setClaudePick(e.target.checked)}
                />
                Let Claude Pick
              </label>
            </div>

            <button
              className="app-start-btn"
              onClick={handleStart}
              disabled={starting || library.length === 0}
            >
              {starting ? (
                <><span className="app-spinner" />Starting…</>
              ) : (
                <>◈ Start Mix</>
              )}
            </button>
          </>
        )}

        {djId && djState?.status === "error" && (
          <button
            className="app-start-btn app-start-btn--reset"
            onClick={() => { setDjId(null); setDjState(null); }}
          >
            ✕ Reset
          </button>
        )}
      </div>

      {startError && (
        <div className="app-error">{startError}</div>
      )}

      {/* Main area */}
      <div className="app-body">
        <LibraryPanel
          playingHash={playingHash}
          queuedHashes={queuedHashes}
          djId={djId}
          onEnqueue={handleEnqueue}
          onLibraryLoaded={setLibrary}
        />

        <div className="app-main">
          {djId ? (
            <MixPlayer
              djId={djId}
              djState={djState}
            />
          ) : (
            <Welcome
              library={library}
              localQueue={localQueue}
              onDequeue={(h) => setLocalQueue((q) => q.filter((x) => x !== h))}
              claudePick={claudePick}
            />
          )}
        </div>
      </div>

      <style>{`
        .app-root {
          height: 100%; display: flex; flex-direction: column; background: var(--bg);
          overflow: hidden;
        }
        .app-topbar {
          display: flex; align-items: center; gap: 10px;
          padding: 6px 14px; border-bottom: 1px solid var(--border);
          background: var(--surface); flex-shrink: 0; min-height: 44px;
        }
        .app-brand {
          font-size: 11px; font-weight: 700; letter-spacing: .2em;
          color: var(--orange); font-family: var(--mono); white-space: nowrap;
        }
        .app-bpm {
          font-family: var(--mono); font-size: 14px; font-weight: 600;
          color: var(--text); white-space: nowrap;
        }
        .app-bpm-unit { font-size: 9px; color: var(--text-3); letter-spacing: .1em; }

        .app-now-playing, .app-deck-b {
          display: flex; flex-direction: column; gap: 1px;
        }
        .app-np-label {
          font-size: 9px; font-weight: 700; letter-spacing: .12em;
          color: var(--text-3); text-transform: uppercase; font-family: var(--mono);
        }
        .app-np-title {
          font-size: 12px; font-weight: 600; color: var(--text); white-space: nowrap;
          max-width: 180px; overflow: hidden; text-overflow: ellipsis;
        }
        .app-np-title--b { color: var(--blue); }

        .app-topbar-spacer { flex: 1; }

        .app-model-row {
          display: flex; align-items: center; gap: 8px;
        }
        .app-select {
          font-size: 12px; padding: 4px 6px;
          background: var(--surface2); border: 1px solid var(--border);
          color: var(--text); border-radius: 3px;
        }
        .app-toggle {
          display: flex; align-items: center; gap: 5px;
          font-size: 12px; color: var(--text-2); cursor: pointer; white-space: nowrap;
        }
        .app-toggle input { cursor: pointer; accent-color: var(--orange); }

        .app-start-btn {
          display: flex; align-items: center; gap: 6px;
          padding: 6px 16px; border-radius: 4px;
          background: var(--orange); color: white;
          font-size: 13px; font-weight: 700; letter-spacing: .02em; white-space: nowrap;
          transition: opacity .15s, transform .1s;
        }
        .app-start-btn--reset { background: var(--surface3); color: var(--red); }
        .app-start-btn:not(:disabled):hover  { opacity: .88; }
        .app-start-btn:not(:disabled):active { transform: scale(.97); }
        .app-start-btn:disabled { opacity: .35; cursor: not-allowed; }
        .app-spinner {
          width: 12px; height: 12px; border-radius: 50%;
          border: 2px solid rgba(255,255,255,.3); border-top-color: white;
          animation: spin .7s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .app-error {
          padding: 6px 14px; background: rgba(255,55,95,.1);
          border-bottom: 1px solid var(--red);
          font-size: 12px; color: var(--red); font-family: var(--mono);
        }

        .app-body {
          flex: 1; display: flex; min-height: 0; overflow: hidden;
        }
        .app-main { flex: 1; min-width: 0; overflow: hidden; }
      `}</style>
    </div>
  );
}

// ── Welcome / pre-session screen ──────────────────────────────────────────────

function Welcome({
  library,
  localQueue,
  onDequeue,
  claudePick,
}: {
  library: LibraryTrack[];
  localQueue: string[];
  onDequeue: (h: string) => void;
  claudePick: boolean;
}) {
  const byHash = Object.fromEntries(library.map((t) => [t.hash, t]));

  return (
    <div className="wlc-root">
      <div className="wlc-hero">
        <ClawdDJ state="idle" size={72} />
        <div className="wlc-hero-text">
          <div className="wlc-title">
            {library.length === 0 ? "Scan a folder to build your library" : "Ready to mix"}
          </div>
          <div className="wlc-sub">
            {library.length === 0
              ? 'Click "Scan Folder" in the library panel to add tracks'
              : claudePick
              ? `${library.length} tracks in library · Claude will pick what plays next`
              : "Double-click tracks in the library to build your queue"}
          </div>
        </div>
      </div>

      {localQueue.length > 0 && (
        <div className="wlc-queue">
          <div className="wlc-queue-header">
            QUEUED TRACKS
            <span className="wlc-queue-count">{localQueue.length}</span>
          </div>
          {localQueue.map((hash, i) => {
            const t = byHash[hash];
            return (
              <div key={hash} className="wlc-queue-row">
                <span className="wlc-queue-idx">{i + 1}</span>
                <span className="wlc-queue-title">
                  {t?.title || hash.slice(0, 8)}
                </span>
                <span className="wlc-queue-bpm">{t?.bpm.toFixed(0)} BPM</span>
                <button className="wlc-queue-rm" onClick={() => onDequeue(hash)}>✕</button>
              </div>
            );
          })}
        </div>
      )}

      <style>{`
        .wlc-root {
          height: 100%; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 32px;
          padding: 40px; overflow-y: auto;
        }
        .wlc-hero {
          display: flex; flex-direction: column; align-items: center; gap: 20px;
          text-align: center;
        }
        .wlc-hero-text { display: flex; flex-direction: column; gap: 8px; }
        .wlc-title { font-size: 22px; font-weight: 700; color: var(--text); }
        .wlc-sub   { font-size: 14px; color: var(--text-2); line-height: 1.5; max-width: 380px; }

        .wlc-queue {
          width: 100%; max-width: 480px;
          background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
          overflow: hidden;
        }
        .wlc-queue-header {
          display: flex; align-items: center; gap: 8px;
          padding: 8px 14px; border-bottom: 1px solid var(--border);
          font-size: 10px; font-weight: 700; letter-spacing: .14em;
          color: var(--text-3); text-transform: uppercase; font-family: var(--mono);
        }
        .wlc-queue-count {
          background: var(--surface2); padding: 1px 6px; border-radius: 3px;
          font-size: 11px; color: var(--text-2);
        }
        .wlc-queue-row {
          display: flex; align-items: center; gap: 8px;
          padding: 7px 14px; border-bottom: 1px solid var(--border);
          font-size: 13px;
        }
        .wlc-queue-row:last-child { border-bottom: none; }
        .wlc-queue-idx  { font-family: var(--mono); font-size: 10px; color: var(--text-3); width: 18px; }
        .wlc-queue-title { flex: 1; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .wlc-queue-bpm  { font-family: var(--mono); font-size: 11px; color: var(--text-2); }
        .wlc-queue-rm   { font-size: 11px; color: var(--text-3); padding: 2px 5px; border-radius: 3px; }
        .wlc-queue-rm:hover { color: var(--red); background: rgba(255,55,95,.1); }
      `}</style>
    </div>
  );
}
