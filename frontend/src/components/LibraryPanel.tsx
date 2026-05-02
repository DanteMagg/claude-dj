import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import type { LibraryScanJob, LibraryTrack } from "../types";

// ── Mini waveform from energy_curve string ────────────────────────────────────

function MiniWave({ curve, active }: { curve: string; active?: boolean }) {
  const BARS = 40;
  const step = Math.max(1, Math.floor(curve.length / BARS));
  const samples: number[] = [];
  for (let i = 0; i < BARS; i++) {
    const idx = Math.min(curve.length - 1, i * step);
    samples.push((parseInt(curve[idx] ?? "5") || 5) / 9);
  }
  return (
    <div className="mw-root">
      {samples.map((h, i) => (
        <div
          key={i}
          className="mw-bar"
          style={{
            height: `${Math.max(15, h * 100)}%`,
            background: active ? "var(--orange)" : "#333",
          }}
        />
      ))}
      <style>{`
        .mw-root {
          display: flex; align-items: flex-end; gap: 1px;
          width: 80px; height: 22px; flex-shrink: 0;
        }
        .mw-bar { flex: 1; border-radius: 1px 1px 0 0; min-width: 1px; }
      `}</style>
    </div>
  );
}

// ── Track row ─────────────────────────────────────────────────────────────────

function TrackRow({
  track,
  isQueued,
  isPlaying,
  onEnqueue,
}: {
  track: LibraryTrack;
  isQueued: boolean;
  isPlaying: boolean;
  onEnqueue: (hash: string) => void;
}) {
  const dur = track.duration_s;
  const mins = Math.floor(dur / 60);
  const secs = Math.round(dur % 60).toString().padStart(2, "0");

  return (
    <div
      className={`tr-row${isPlaying ? " tr-row--playing" : ""}${isQueued ? " tr-row--queued" : ""}`}
      onDoubleClick={() => onEnqueue(track.hash)}
      title="Double-click to add to queue"
    >
      <div className="tr-playing-indicator">
        {isPlaying ? "▶" : ""}
      </div>

      <div className="tr-info">
        <div className="tr-title">{track.title || track.path.split("/").pop()?.replace(/\.[^.]+$/, "")}</div>
        <div className="tr-artist">{track.artist || "—"}</div>
      </div>

      <MiniWave curve={track.energy_curve} active={isPlaying} />

      <div className="tr-meta">
        <span className="tr-bpm">{track.bpm.toFixed(0)}</span>
        <span className="tr-key">{track.key_camelot}</span>
        <span className="tr-dur">{mins}:{secs}</span>
      </div>

      <button
        className={`tr-queue-btn${isQueued ? " tr-queue-btn--active" : ""}`}
        onClick={() => onEnqueue(track.hash)}
        title="Add to queue"
      >
        {isQueued ? "✓" : "+"}
      </button>

      <style>{`
        .tr-row {
          display: flex; align-items: center; gap: 8px;
          padding: 6px 10px; border-bottom: 1px solid var(--border);
          cursor: default; transition: background .1s;
        }
        .tr-row:hover { background: var(--surface2); }
        .tr-row--playing { background: var(--orange-lo) !important; }
        .tr-row--queued .tr-title { color: var(--blue); }

        .tr-playing-indicator {
          width: 12px; font-size: 8px; color: var(--orange); flex-shrink: 0;
        }
        .tr-info { flex: 1; min-width: 0; }
        .tr-title {
          font-size: 12px; font-weight: 500; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; color: var(--text);
        }
        .tr-artist {
          font-size: 10px; color: var(--text-3); white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis;
        }
        .tr-meta {
          display: flex; flex-direction: column; align-items: flex-end; gap: 1px; flex-shrink: 0;
        }
        .tr-bpm { font-family: var(--mono); font-size: 11px; color: var(--text-2); }
        .tr-key { font-family: var(--mono); font-size: 10px; color: var(--green); }
        .tr-dur { font-family: var(--mono); font-size: 10px; color: var(--text-3); }

        .tr-queue-btn {
          width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
          background: var(--surface3); border: 1px solid var(--border2);
          font-size: 13px; color: var(--text-2); line-height: 1;
          display: flex; align-items: center; justify-content: center;
          transition: background .1s, color .1s;
        }
        .tr-queue-btn:hover { background: var(--orange-lo); color: var(--orange); border-color: var(--orange); }
        .tr-queue-btn--active { background: var(--blue-lo); color: var(--blue); border-color: var(--blue); }
      `}</style>
    </div>
  );
}

// ── LibraryPanel ──────────────────────────────────────────────────────────────

interface Props {
  playingHash: string | null;
  queuedHashes: string[];
  djId: string | null;
  onEnqueue: (hash: string) => void;
  onLibraryLoaded?: (tracks: LibraryTrack[]) => void;
}

export default function LibraryPanel({
  playingHash,
  queuedHashes,
  djId,
  onEnqueue,
  onLibraryLoaded,
}: Props) {
  const [tracks, setTracks]   = useState<LibraryTrack[]>([]);
  const [scanId, setScanId]   = useState<string | null>(null);
  const [scan, setScan]       = useState<LibraryScanJob | null>(null);
  const [filter, setFilter]   = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLibrary = useCallback(async () => {
    try {
      const res  = await apiFetch("/api/library");
      const data = (await res.json()) as { tracks: LibraryTrack[] };
      setTracks(data.tracks);
      onLibraryLoaded?.(data.tracks);
    } catch { /* ignore */ }
  }, [onLibraryLoaded]);

  useEffect(() => { void fetchLibrary(); }, [fetchLibrary]);

  // Poll scan progress
  useEffect(() => {
    if (!scanId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res  = await apiFetch(`/api/library/scan/${scanId}`);
        const job  = (await res.json()) as LibraryScanJob;
        setScan(job);
        if (job.status === "done" || job.status === "error") {
          clearInterval(pollRef.current!);
          if (job.status === "done") void fetchLibrary();
        }
      } catch { /* ignore */ }
    }, 1000);
    return () => clearInterval(pollRef.current!);
  }, [scanId, fetchLibrary]);

  const handleScan = async () => {
    // Electron: show native folder picker if available
    const folder: string | null = await (window as unknown as { electronAPI?: { openFolder: () => Promise<string | null> } })
      .electronAPI?.openFolder() ?? null;

    const target = folder ?? prompt("Folder path to scan:");
    if (!target) return;

    setScan({ status: "running", progress: 0, total: 0, known: 0, new: 0, error: null });
    try {
      const res  = await apiFetch("/api/library/scan", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ folder: target }),
      });
      const data = (await res.json()) as { scan_id: string };
      setScanId(data.scan_id);
    } catch (e) {
      setScan({ status: "error", progress: 0, total: 0, known: 0, new: 0, error: String(e) });
    }
  };

  const enqueueViaApi = async (hash: string) => {
    onEnqueue(hash);
    if (djId) {
      try {
        await apiFetch(`/api/dj/${djId}/queue`, {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ hash }),
        });
      } catch { /* ignore */ }
    }
  };

  const filtered = filter
    ? tracks.filter(
        (t) =>
          t.title.toLowerCase().includes(filter.toLowerCase()) ||
          t.artist.toLowerCase().includes(filter.toLowerCase()) ||
          t.key_camelot.toLowerCase().includes(filter.toLowerCase()),
      )
    : tracks;

  const scanning = scan?.status === "running";

  return (
    <div className="lib-root">
      {/* Header */}
      <div className="lib-header">
        <span className="lib-title">LIBRARY</span>
        <span className="lib-count">{tracks.length}</span>
        <button className="lib-scan-btn" onClick={handleScan} disabled={scanning}>
          {scanning ? "Scanning…" : "Scan Folder"}
        </button>
      </div>

      {/* Scan progress */}
      {scan && (
        <div className={`lib-scan-bar${scan.status === "error" ? " lib-scan-bar--error" : ""}`}>
          {scan.status === "error" ? (
            <span className="lib-scan-err">{scan.error}</span>
          ) : (
            <>
              <div className="lib-scan-track">
                <div
                  className="lib-scan-fill"
                  style={{ width: scan.total > 0 ? `${(scan.progress / scan.total) * 100}%` : "0%" }}
                />
              </div>
              <span className="lib-scan-label">
                {scan.status === "done"
                  ? `Done · ${scan.new} new, ${scan.known} cached`
                  : `${scan.progress} / ${scan.total} · ${scan.new} new`}
              </span>
            </>
          )}
        </div>
      )}

      {/* Search */}
      <div className="lib-search-wrap">
        <input
          className="lib-search"
          placeholder="Filter by title, artist, key…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {/* Column headers + queue-all */}
      <div className="lib-cols">
        <span style={{ width: 12 }} />
        <span className="lib-col-hd" style={{ flex: 1 }}>TRACK</span>
        <span className="lib-col-hd" style={{ width: 80 }}>WAVE</span>
        <span className="lib-col-hd" style={{ width: 54, textAlign: "right" }}>BPM / KEY</span>
        <button
          className="lib-queue-all-btn"
          title="Queue all visible tracks"
          disabled={filtered.length === 0}
          onClick={() => filtered.forEach(t => enqueueViaApi(t.hash))}
        >
          +ALL
        </button>
      </div>

      {/* Track list */}
      <div className="lib-list">
        {filtered.length === 0 ? (
          <div className="lib-empty">
            {tracks.length === 0
              ? "Scan a folder to add tracks"
              : "No tracks match the filter"}
          </div>
        ) : (
          filtered.map((t) => (
            <TrackRow
              key={t.hash}
              track={t}
              isPlaying={t.hash === playingHash}
              isQueued={queuedHashes.includes(t.hash)}
              onEnqueue={enqueueViaApi}
            />
          ))
        )}
      </div>

      <style>{`
        .lib-root {
          width: 300px; flex-shrink: 0; display: flex; flex-direction: column;
          border-right: 1px solid var(--border); background: var(--surface);
          overflow: hidden;
        }
        .lib-header {
          display: flex; align-items: center; gap: 6px;
          padding: 8px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0;
        }
        .lib-title {
          font-size: 10px; font-weight: 700; letter-spacing: .14em;
          color: var(--text-3); text-transform: uppercase; font-family: var(--mono);
          flex: 1;
        }
        .lib-count {
          font-family: var(--mono); font-size: 11px; color: var(--text-2);
          background: var(--surface2); padding: 1px 6px; border-radius: 3px;
        }
        .lib-scan-btn {
          font-size: 11px; padding: 3px 10px; border-radius: 3px;
          background: var(--surface3); color: var(--text-2);
          border: 1px solid var(--border2); transition: color .1s, border-color .1s;
        }
        .lib-scan-btn:not(:disabled):hover { color: var(--orange); border-color: var(--orange); }
        .lib-scan-btn:disabled { opacity: .4; cursor: not-allowed; }

        .lib-scan-bar {
          display: flex; align-items: center; gap: 8px;
          padding: 5px 12px; background: var(--surface2);
          border-bottom: 1px solid var(--border); flex-shrink: 0;
        }
        .lib-scan-bar--error { background: rgba(255,55,95,.07); }
        .lib-scan-track {
          flex: 1; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden;
        }
        .lib-scan-fill { height: 100%; background: var(--orange); transition: width .4s; }
        .lib-scan-label { font-family: var(--mono); font-size: 10px; color: var(--text-2); white-space: nowrap; }
        .lib-scan-err  { font-family: var(--mono); font-size: 10px; color: var(--red); }

        .lib-search-wrap { padding: 6px 10px; flex-shrink: 0; }
        .lib-search {
          width: 100%; font-size: 12px; background: var(--surface2);
          border: 1px solid var(--border); border-radius: 3px;
          padding: 5px 8px; color: var(--text);
        }
        .lib-search:focus { border-color: var(--border2); outline: none; }

        .lib-cols {
          display: flex; align-items: center; gap: 8px;
          padding: 4px 10px; border-bottom: 1px solid var(--border);
          flex-shrink: 0;
        }
        .lib-col-hd {
          font-size: 9px; font-weight: 600; letter-spacing: .1em;
          color: var(--text-3); text-transform: uppercase; font-family: var(--mono);
        }

        .lib-queue-all-btn {
          font-family: var(--mono); font-size: 9px; font-weight: 700;
          letter-spacing: .08em; padding: 2px 6px; border-radius: 3px;
          background: var(--surface3); color: var(--text-3);
          border: 1px solid var(--border2); white-space: nowrap;
          transition: color .1s, border-color .1s;
        }
        .lib-queue-all-btn:not(:disabled):hover { color: var(--blue); border-color: var(--blue); }
        .lib-queue-all-btn:disabled { opacity: .3; cursor: not-allowed; }

        .lib-list { flex: 1; overflow-y: auto; }
        .lib-empty {
          padding: 40px 20px; text-align: center;
          font-size: 12px; color: var(--text-3); font-family: var(--mono);
          letter-spacing: .04em;
        }
      `}</style>
    </div>
  );
}
